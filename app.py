from flask import Flask, render_template, flash, request  # + request
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, RadioField
from wtforms.fields import DateField
from wtforms.validators import DataRequired, NumberRange, Optional  # no InputRequired
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from PIL import Image  # required by qrcode[pil]
import io
import base64
import pytz
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-to-a-long-random-string'

# ----- helpers -----
def default_start_local(tz_name='Europe/Berlin'):
    """Return (date, hour, minute) rounded up to the next hour local time."""
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    next_top = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return next_top.date(), next_top.hour, 0

# ----- Form -----
class EventForm(FlaskForm):
    # Start (now Optional; we'll fill defaults ourselves)
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


@app.route('/', methods=['GET', 'POST'])
def index():
    form = EventForm()
    qr_code = None
    ics_content = None
    ics_b64 = None

    # Pre-fill defaults for initial render (and re-render after errors)
    if request.method == 'GET':
        d, h, m = default_start_local('Europe/Berlin')
        if form.date.data is None:
            form.date.data = d
        if form.hour.data is None:
            form.hour.data = h
        if form.minutes.data is None:
            form.minutes.data = m

    if form.validate_on_submit():
        try:
            title = form.title.data.strip()
            description = (form.description.data or "").strip()
            location = (form.location.data or "").strip()
            reminder_minutes = form.reminder.data or 0

            local_tz = pytz.timezone('Europe/Berlin')

            # Fallbacks if user left any start fields empty
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

            if mode == 'duration':
                dh = form.duration_hours.data or 0
                dm = form.duration_minutes.data or 0
                if dh == 0 and dm == 0:
                    flash("Duration must be greater than 0 minutes.", "danger")
                    return render_template('index.html', form=form, qr_code=None, ics_content=None, ics_b64=None)
                end_utc = start_utc + timedelta(hours=dh, minutes=dm)

            elif mode == 'end':
                if not (form.end_date.data is not None and
                        form.end_hour.data is not None and
                        form.end_minutes.data is not None):
                    flash("Please provide end date, hour, and minutes.", "danger")
                    return render_template('index.html', form=form, qr_code=None, ics_content=None, ics_b64=None)

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
                    flash("End time must be after the start time.", "danger")
                    return render_template('index.html', form=form, qr_code=None, ics_content=None, ics_b64=None)
            else:
                flash("Unknown mode for end time.", "danger")
                return render_template('index.html', form=form, qr_code=None, ics_content=None, ics_b64=None)

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
            flash(f"Error: {str(e)}", "danger")

    return render_template('index.html', form=form, qr_code=qr_code, ics_content=ics_content, ics_b64=ics_b64)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
