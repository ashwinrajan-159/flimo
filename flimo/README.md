<div align="center">
  <h1>🍿 Flimo</h1>
  <p><strong>An Intelligent, Cinematic AI-Powered Movie Discovery Engine</strong></p>

  [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](#)
  [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
  [![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)](#)
  [![FAISS](https://img.shields.io/badge/FAISS-AI-FF6F00?style=for-the-badge)](#)
  [![HuggingFace](https://img.shields.io/badge/Transformers-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)](#)
</div>

---

Flimo is a full-stack, AI-powered content recommendation platform designed to rival commercial streaming architectures. Featuring intelligent natural language processing (NLP), hybrid semantic search personalization, community engagement tools, and a bold **Cinematic Editorial UI**.

Unlike standard keyword search engines, Flimo understands *concepts*. Ask for "dark thriller movies set in space," and the locally embedded `all-MiniLM-L6-v2` transformer model will instantly retrieve semantically matching content via **FAISS** vector indexing—no exact keyword matches required.

---

## ✨ Key Features

### 🧠 Deep Semantic AI Search
- Replaces rigid SQL queries with **Transformer-based text embeddings**.
- Parses complex queries (e.g., *"funny romantic movies with action"*).
- Automatically routes and detects intents (Themes, Entities, Moods).

### 🎬 Hybrid Personalization
- **"Because You Watched..."**: Analyzes your personalized view history, creates a composite vector of your tastes, and dynamically fetches highly-rated, highly-popular recommendations from the vector store.
- **Smart Filtering**: Gates recommendations strictly by minimum `rating` (>= 7.0) and `popularity` to ensure premium discovery.

### ✨ Cinematic Editorial UI
- **Premium Design System**: Uses sophisticated OKLCH color palettes, sharp edges, and modern typography (Inter/Outfit).
- **Dynamic Experiences**: Seamless transitions, hover-states, glassmorphism, and responsive grid layouts.

### 🌐 Scalable Content Ingestion
- Ingests top-rated, popular, and trending movies/series from **TMDB**.
- Pulls trending trailers directly from **YouTube**.
- Supports massive database expansions via deep `--discover` and `--multilingual` data pipelines.

---

## 🏗️ Architecture & Tech Stack

- **Backend**: Python 3.10+ & FastAPI (Async API design)
- **Vector DB / Search**: FAISS (Meta's Similarity Search) & `sentence-transformers` (`all-MiniLM-L6-v2`)
- **Relational DB**: SQLite (with WAL mode & indexed B-Trees for rapid filtering)
- **Frontend**: Vanilla JavaScript (ES6), HTML5, and pure CSS3 (No heavy frontend frameworks)
- **External Providers**: TMDB API, YouTube Data v3 API

---

## 🚀 Getting Started

### 1️⃣ Prerequisites
- **Python 3.10+** installed
- API Keys for TMDB and YouTube

### 2️⃣ Virtual Environment Setup
It is highly recommended to run this inside a virtual environment.

```bash
# Create the environment
python -m venv venv

# Activate it (Mac/Linux)
source venv/bin/activate

# Activate it (Windows)
venv\Scripts\activate
```

### 3️⃣ Installation
Once the environment is active:
```bash
pip install -r requirements.txt
```

### 4️⃣ Configuration
Create a `.env` file in the root of the project and add your API keys:
```env
TMDB_API_KEY=your_tmdb_api_key_here
YOUTUBE_API_KEY=your_youtube_api_key_here
```

---

## 🛠️ Data Pipeline & Initialization

Before running the server, you need to populate your local database and train the AI vectors.

### Step 1: Ingest Content
This step reaches out to TMDB & YouTube to build your relational SQLite database (`data/content.db`).
```bash
# Standard Ingestion (Populates ~1,000+ popular movies, series, and trailers)
python -m src.ingest --all

# Deep Discovery Ingestion (Optional: Fetches up to 10,000 movies)
python -m src.ingest --discover 500
```

### Step 2: Generate AI Vectors
Once you have data, you must generate the semantic vector definitions for the FAISS database (`data/vectors.faiss`).
```bash
python -m src.embed
```
*Note: This runs locally on your CPU/GPU and may take a few minutes depending on the size of your database. It only needs to process un-embedded content.*

---

## ▶️ Running the Application

Start the FastAPI application server:
```bash
uvicorn src.api:app --reload
```

- **Frontend UI**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 🧪 Example API Usage
You can programmatically test the AI semantic search engine:
```bash
curl -X POST http://127.0.0.1:8000/search \
-H "Content-Type: application/json" \
-d '{ "base_prompt": "dark thriller", "mood": "dark" }'
```

---

## 🐳 Docker Support (Optional)
To run isolated without installing Python dependencies manually:
```bash
docker-compose up --build
```
Then visit `http://localhost:8000`.
