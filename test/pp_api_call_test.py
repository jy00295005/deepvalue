import os
import json
from perplexity import Perplexity

TICKERS = ["AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "GOOG"]

PROMPT = f"""
For the last 2 months, estimate the next strongest support level for each ticker: {", ".join(TICKERS)}.

Requirements:
- Use recent daily price info from reliable sources.
- Report support as a PRICE RANGE (not a single number).
- Output JSON array with:
  ticker, as_of_date, last_price, support_main, support_alt (2 items), notes
- If you can't find reliable sources for a ticker, return missing_data=true for it (do NOT guess).
- Keep it concise.
"""

def main():
    if not os.getenv("PERPLEXITY_API_KEY"):
        raise RuntimeError("Missing PERPLEXITY_API_KEY env var.")

    client = Perplexity()

    completion = client.chat.completions.create(
        model="sonar",
        messages=[
            {"role": "system", "content": "Be precise and concise. Prefer reliable sources."},
            {"role": "user", "content": PROMPT},
        ],
        # 想更快：把检索上下文压小（如果你的账号/版本支持该字段）
        web_search_options={"search_context_size": "medium"},
        temperature=0.1,
    )

    # 主回答
    print("\n=== MODEL OUTPUT ===")
    print(completion.choices[0].message.content)

    # 可选：打印搜索结果（字段是否存在取决于模型/账号返回）
    sr = getattr(completion, "search_results", None)
    if sr:
        print("\n=== SEARCH RESULTS (top) ===")
        for item in sr[:5]:
            title = getattr(item, "title", "")
            url = getattr(item, "url", "")
            date = getattr(item, "date", "")
            print(f"- {date} {title} | {url}")

if __name__ == "__main__":
    main()
