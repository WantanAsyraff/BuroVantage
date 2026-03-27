🏛️ BuroVantage [VLM]

BuroVantage is an enterprise-grade PDF extraction engine designed for high-precision data harvesting. Unlike traditional OCR that relies on text layers, BuroVantage leverages state-of-the-art Vision Language Models (VLM) to "see" and interpret document layouts, complex tables, and handwritten forms just as a human would.

Developed during an IT internship at Sarawak Information Systems (SAINS), this tool bridges the gap between unstructured physical paperwork and structured digital databases.
🚀 Key Features

    Visual Intelligence: Uses Gemini 2.0/3, GPT-4o, and Pixtral to handle skewed scans, overlapping text, and complex table borders.

    Dynamic Schema Designer: A built-in Web UI to define "Fields" (Headers, Keys, and AI Instructions) without touching the code.

    VLM Multi-Provider Support: Switch between Google Gemini, OpenAI, and Mistral through the settings panel.

    Dockerized Architecture: Fully containerized for easy deployment on Arch Linux/Hyprland or server environments.

    Structured Output: Direct-to-CSV extraction optimized for immediate import into Excel or SQL databases.

🛠️ Tech Stack

    Backend: Python 3.10+, Flask

    Frontend: Vanilla JS, Jinja2, DM Sans & DM Mono Typography

    Core Engine: google-genai, openai, mistralai

    Infrastructure: Docker & Docker-Compose

📦 Getting Started
1. Clone the Repository
Bash

git clone https://github.com/WantanAsyraff/BuroVantage.git
cd BuroVantage

2. Configure Environment

Create a config.json in the root directory or use the Settings tab in the Web UI to add your API keys:
JSON

{
  "provider": "gemini",
  "model": "gemini-3-flash",
  "api_key": "YOUR_API_KEY_HERE"
}

3. Launch with Docker
Bash

# Give Docker permission to access your X11/Wayland display (for GUI)
xhost +local:docker

# Build and run
docker-compose up --build

Access the dashboard at http://localhost:5000.
📁 Project Structure

    web_designer.py: The main Flask entry point and API handler.

    processor.py: The VLM logic and PDF-to-Image conversion engine.

    templates/: UI layouts (BuroVantage industrial theme).

    pdfs/: Input directory for your documents.

    schema.json: Stores your custom extraction instructions.

📜 License

This project is licensed under the Apache License 2.0. It is free for personal and commercial use, providing patent protection and clear contribution guidelines—making it ideal for government-linked and enterprise environments.
