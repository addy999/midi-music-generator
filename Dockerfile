FROM python:3.12-slim

WORKDIR /app

RUN apt-get update 
RUN apt-get install -y curl fluidsynth

RUN curl 'https://raw.githubusercontent.com/spessasus/SpessaSynth/master/soundfonts/GeneralUserGS.sf3' -o GeneralUserGS.sf3

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
COPY pyproject.toml uv.lock .python-version ./
RUN uv python install
RUN uv sync
RUN uv venv

COPY . /app

EXPOSE 5001
CMD ["uv", "run", "flask", "run", "--host=0.0.0.0", "--port=5001"]
