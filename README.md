# Element Monitor Telegram Bot

A Telegram bot that monitors web pages for element text changes. The bot can handle multiple users (up to 5 concurrent sessions) and will notify users when element text changes or elements disappear on their monitored pages.

## Features

- Monitor web pages for element text changes
- Support for multiple CSS selectors
- Fixed 60-second refresh interval
- Automatic session timeout after 12 hours
- Concurrent monitoring for up to 2 users
- Cloudflare bypass using cloudscraper
- Docker support with health check endpoint

## Prerequisites

- Docker and Docker Compose
- A Telegram Bot Token (get one from [@BotFather](https://t.me/botfather))

## Setup

1. Clone this repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create a `.env` file with your Telegram Bot Token:
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

3. Build and run the container using Docker Compose:
```bash
docker-compose up --build
```

## Usage

1. Start a conversation with your bot on Telegram
2. Send the `/start` command to begin setting up monitoring
3. Follow the bot's prompts to provide:
   - The URL to monitor
   - CSS selector(s) for the element(s) to watch (one per line)
4. The bot will start monitoring and notify you when:
   - Any element text changes
   - Any elements disappear
   - An error occurs
   - The 12-hour monitoring period ends

## Commands

- `/start` - Start a new monitoring session
- `/stop` - Stop the current monitoring session
- `/cancel` - Cancel the setup process

## Technical Details

- Built with Python 3.9
- Uses cloudscraper for Cloudflare bypass
- SQLite database for session storage
- FastAPI health check endpoint on port 8080
- Containerized with Docker

## Health Check

The application exposes a health check endpoint at:
```
http://localhost:8080/health
```

## Limitations

- Maximum 2 concurrent monitoring sessions
- Each session times out after 12 hours
- Fixed refresh interval: 60 seconds

## Error Handling

The bot will automatically stop monitoring and notify users when:
- The page becomes unreachable
- Element selectors are not found
- Cloudflare challenges cannot be bypassed
- Any other error occurs during monitoring

## Data Persistence

The SQLite database is persisted using a Docker volume. The database file is stored in the `data` directory:
```
./data:/app/data
```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 