# Event QR Code Generator

A lightweight web application that generates QR codes for calendar events (ICS). Users can scan the QR code to instantly add events to their smartphone calendars.

**Live Demo:** [https://qr.danielsi.ch](https://qr.danielsi.ch)

## 🚀 Features

- **Instant Generation**: Create calendar events with a Title, Description, Location, and Time.
- **Flexible Timing**: Define event length by duration or specific end date/time.
- **Smart Reminders**: Set custom reminders (alarms) for the event.
- **Universal Format**: Generates standard `.ics` files compatible with iOS, Google Calendar, and Outlook.
- **Fast & Modern**: Built with **FastAPI** for high performance.
- **Clean UI**: Responsive design tailored for quick usage.

## 🛠️ Tech Stack

- **Python 3.12**
- **FastAPI**: Modern, fast (high-performance) web framework.
- **Uvicorn**: ASGI web server.
- **WTForms**: Form validation.
- **icalendar**: ICS file generation.
- **qrcode**: QR code image generation.
- **Render**: Cloud hosting.

## 🏃 Local Development

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/danielsich/EventQRCodes.git
    cd EventQRCodes
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    uvicorn main:app --reload
    ```
    Visit `http://127.0.0.1:8000` in your browser.

## 📦 Deployment

This project includes a `render.yaml` for easy deployment on [Render](https://render.com).

1.  Push your code to **GitHub/GitLab**.
2.  Create a **New Blueprint Instance** on Render.
3.  Connect your repository.
4.  Render will automatically detect the `render.yaml` and deploy using **Uvicorn**.

## 👨‍💻 Author

**Daniel Sich**  
Built as a personal utility to simplify event sharing.
