import io
import base64
import uuid
import pytz
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

from wtforms import Form, StringField, IntegerField, RadioField, SubmitField
from wtforms.fields import DateField
from wtforms.validators import DataRequired, NumberRange, Optional

from icalendar import Calendar, Event, Alarm
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from PIL import Image

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ----- Helpers -----
def default_start_local(tz_name='Europe/Berlin'):
    """Return (date, hour, minute) rounded up to the next hour local time."""
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    next_top = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return next_top.date(), next_top.hour, 0

# ----- Form -----
# Note: standard WTForms Form, not FlaskForm (which requires Flask session/secret key)
class EventForm(Form):
    # Start
    date = DateField('Start Date', format='%Y-%m-%d', validators=[Optional()])
    hour = IntegerField(
        'Start Hour (0-23)',
        validators=[Optional(), NumberRange(min=0, max=23)],
        render_kw={"min": 0, "max": 23}
    )
    minutes = IntegerField(
        'Start Minutes (0-59)',
        validators=[Optional(), NumberRange(min=0, max=59)],
        render_kw={"min": 0, "max": 59}
    )

    title = StringField('Title', validators=[DataRequired()])
    description = StringField('Description')
    location = StringField('Location (address or link)')
    reminder = IntegerField('Reminder (minutes before)', default=15, validators=[NumberRange(min=0)])

    mode = RadioField(
        'How do you want to set the end?',
        choices=[('duration', 'By duration'), ('end', 'By end date/time')],
        default='duration'
    )

    duration_hours = IntegerField('Duration Hours', validators=[Optional(), NumberRange(min=0, max=240)],
                                  render_kw={"min": 0, "max": 240})
    duration_minutes = IntegerField('Duration Minutes', validators=[Optional(), NumberRange(min=0, max=59)],
                                    render_kw={"min": 0, "max": 59})

    end_date = DateField('End Date', format='%Y-%m-%d', validators=[Optional()])
    end_hour = IntegerField('End Hour (0-23)', validators=[Optional(), NumberRange(min=0, max=23)],
                            render_kw={"min": 0, "max": 23})
    end_minutes = IntegerField('End Minutes (0-59)', validators=[Optional(), NumberRange(min=0, max=59)],
                               render_kw={"min": 0, "max": 59})

    submit = SubmitField('Generate QR Code')
    
    # We can handle CSRF manually or ignore it for this simple app. 
    # FlaskForm does it automatically. Standard Form does not.

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    d, h, m = default_start_local('Europe/Berlin')
    form = EventForm()
    # Pre-fill defaults
    if form.date.data is None:
        form.date.data = d
    if form.hour.data is None:
        form.hour.data = h
    if form.minutes.data is None:
        form.minutes.data = m
        
    return templates.TemplateResponse("index.html", {
        "request": request,
        "form": form,
        "qr_code": None,
        "ics_content": None,
        "ics_b64": None,
        "messages": [] 
    })

@app.post("/", response_class=HTMLResponse)
async def index_post(request: Request):
    form_data = await request.form()
    form = EventForm(form_data)
    
    qr_code = None
    ics_content = None
    ics_b64 = None
    messages = []

    if request.method == 'POST' and form.validate():
        try:
            title = form.title.data.strip()
            description = (form.description.data or "").strip()
            location = (form.location.data or "").strip()
            reminder_minutes = form.reminder.data or 0

            local_tz = pytz.timezone('Europe/Berlin')

            # Fallbacks
            def_date, def_hour, def_min = default_start_local('Europe/Berlin')
            start_date = form.date.data or def_date
            start_hour = form.hour.data if form.hour.data is not None else def_hour
            start_min = form.minutes.data if form.minutes.data is not None else def_min

            start_local = datetime(
                year=start_date.year,
                month=start_date.month,
                day=start_date.day,
                hour=start_hour,
                minute=start_min,
            )
            start_local = local_tz.localize(start_local)
            start_utc = start_local.astimezone(pytz.utc)

            # ----- Determine end time -----
            mode = form.mode.data

            end_utc = None
            
            if mode == 'duration':
                dh = form.duration_hours.data or 0
                dm = form.duration_minutes.data or 0
                if dh == 0 and dm == 0:
                    messages.append(("danger", "Duration must be greater than 0 minutes."))
                else:
                    end_utc = start_utc + timedelta(hours=dh, minutes=dm)

            elif mode == 'end':
                # Note: WTForms might leave data as None if empty
                if not (form.end_date.data and form.end_hour.data is not None and form.end_minutes.data is not None):
                     messages.append(("danger", "Please provide end date, hour, and minutes."))
                else:
                    end_local = datetime(
                        year=form.end_date.data.year,
                        month=form.end_date.data.month,
                        day=form.end_date.data.day,
                        hour=form.end_hour.data,
                        minute=form.end_minutes.data,
                    )
                    end_local = local_tz.localize(end_local)
                    end_utc = end_local.astimezone(pytz.utc)

                    if end_utc <= start_utc:
                        messages.append(("danger", "End time must be after the start time."))
                        end_utc = None # invalid
            else:
                 messages.append(("danger", "Unknown mode for end time."))

            if not messages and end_utc:
                # ----- Build ICS -----
                cal = Calendar()
                cal.add('prodid', '-//Event QR Code Generator//example//')
                cal.add('version', '2.0')
                cal.add('method', 'PUBLISH')

                event = Event()
                event.add('uid', str(uuid.uuid4()))
                event.add('dtstamp', datetime.now(pytz.utc))
                event.add('dtstart', start_utc)
                event.add('dtend', end_utc)
                event.add('summary', title)
                if description:
                    event.add('description', description)
                if location:
                    event.add('location', location)

                if reminder_minutes > 0:
                    alarm = Alarm()
                    alarm.add('trigger', timedelta(minutes=-reminder_minutes))
                    alarm.add('action', 'DISPLAY')
                    alarm.add('description', f'Reminder: {title}')
                    event.add_component(alarm)

                cal.add_component(event)

                ics_bytes = cal.to_ical()
                ics_content = ics_bytes.decode('utf-8', errors='replace')
                ics_b64 = base64.b64encode(ics_bytes).decode('ascii')

                qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=10, border=4)
                qr.add_data(ics_bytes)
                qr.make(fit=True)
                img = qr.make_image(fill_color='black', back_color='white')

                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                qr_code = base64.b64encode(buffered.getvalue()).decode('utf-8')

        except Exception as e:
            messages.append(("danger", f"Error: {str(e)}"))
            
    return templates.TemplateResponse("index.html", {
        "request": request,
        "form": form,
        "qr_code": qr_code,
        "ics_content": ics_content,
        "ics_b64": ics_b64,
        "messages": messages
    })

if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
