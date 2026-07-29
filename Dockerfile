FROM apify/actor-python-playwright:3.11

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN python3 -m scrapling install 2>&1 || echo "scrapling install failed, will use Playwright fallback"

COPY . ./
