"""
GSC Agent — Pulls keyword data from Google Search Console API.
Identifies quick wins (positions 11-30) and underperforming pages.
"""

import os
import json
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


class GSCAgent:
    def __init__(self, site_url: str):
        self.site_url = site_url
        self.credentials_path = os.getenv("GSC_CREDENTIALS_PATH", "config/gsc_credentials.json")
        self.service = None

    def _init_service(self):
        """Initialize Google Search Console API client."""
        creds = Credentials.from_service_account_file(
            self.credentials_path,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        self.service = build("searchconsole", "v1", credentials=creds)

    async def run(self) -> dict:
        """Fetch and analyse GSC data."""
        try:
            self._init_service()

            end_date = datetime.now() - timedelta(days=3)  # GSC has ~3 day lag
            start_date = end_date - timedelta(days=28)

            # Fetch keyword data
            keyword_data = self._fetch_keywords(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )

            # Fetch page-level data
            page_data = self._fetch_pages(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            )

            # Identify quick wins (positions 11-30 with decent impressions)
            quick_wins = [
                kw for kw in keyword_data
                if 11 <= kw["position"] <= 30 and kw["impressions"] >= 10
            ]
            quick_wins.sort(key=lambda x: x["impressions"], reverse=True)

            # Identify high-impression, low-CTR keywords (opportunity to improve titles/meta)
            low_ctr = [
                kw for kw in keyword_data
                if kw["impressions"] >= 50 and kw["ctr"] < 0.03 and kw["position"] <= 15
            ]

            # Top performing pages
            top_pages = sorted(page_data, key=lambda x: x["clicks"], reverse=True)[:10]

            # Pages with high impressions but low clicks
            weak_pages = [
                p for p in page_data
                if p["impressions"] >= 100 and p["ctr"] < 0.02
            ]

            return {
                "period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "total_keywords": len(keyword_data),
                "total_pages": len(page_data),
                "quick_wins": quick_wins[:20],
                "low_ctr_keywords": low_ctr[:10],
                "top_pages": top_pages,
                "weak_pages": weak_pages[:10],
                "summary": {
                    "total_clicks": sum(k["clicks"] for k in keyword_data),
                    "total_impressions": sum(k["impressions"] for k in keyword_data),
                    "avg_position": round(
                        sum(k["position"] * k["impressions"] for k in keyword_data)
                        / max(sum(k["impressions"] for k in keyword_data), 1), 1
                    ),
                },
            }

        except FileNotFoundError:
            print("   ⚠️  GSC credentials not found. Using demo data.")
            return self._demo_data()
        except Exception as e:
            print(f"   ⚠️  GSC error: {e}. Using demo data.")
            return self._demo_data()

    def _fetch_keywords(self, start_date: str, end_date: str) -> list:
        """Fetch keyword-level performance from GSC."""
        response = self.service.searchanalytics().query(
            siteUrl=self.site_url,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["query"],
                "rowLimit": 500,
            },
        ).execute()

        return [
            {
                "keyword": row["keys"][0],
                "clicks": row["clicks"],
                "impressions": row["impressions"],
                "ctr": round(row["ctr"], 4),
                "position": round(row["position"], 1),
            }
            for row in response.get("rows", [])
        ]

    def _fetch_pages(self, start_date: str, end_date: str) -> list:
        """Fetch page-level performance from GSC."""
        response = self.service.searchanalytics().query(
            siteUrl=self.site_url,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page"],
                "rowLimit": 200,
            },
        ).execute()

        return [
            {
                "page": row["keys"][0],
                "clicks": row["clicks"],
                "impressions": row["impressions"],
                "ctr": round(row["ctr"], 4),
                "position": round(row["position"], 1),
            }
            for row in response.get("rows", [])
        ]

    def _demo_data(self) -> dict:
        """Fallback demo data when GSC credentials are not configured."""
        return {
            "period": "Demo data (configure GSC credentials to get real data)",
            "total_keywords": 45,
            "total_pages": 8,
            "quick_wins": [
                {"keyword": "hair salon jurong point", "clicks": 12, "impressions": 280, "ctr": 0.043, "position": 14.2},
                {"keyword": "anti frizz treatment singapore", "clicks": 8, "impressions": 190, "ctr": 0.042, "position": 18.5},
                {"keyword": "hair rescue treatment singapore", "clicks": 15, "impressions": 340, "ctr": 0.044, "position": 12.1},
                {"keyword": "hair salon bishan junction 8", "clicks": 6, "impressions": 150, "ctr": 0.040, "position": 22.3},
                {"keyword": "best hair treatment singapore frizzy", "clicks": 4, "impressions": 120, "ctr": 0.033, "position": 25.8},
            ],
            "low_ctr_keywords": [
                {"keyword": "hair salon singapore", "clicks": 5, "impressions": 820, "ctr": 0.006, "position": 11.2},
                {"keyword": "hair treatment singapore", "clicks": 9, "impressions": 650, "ctr": 0.014, "position": 8.4},
            ],
            "top_pages": [
                {"page": "https://coulisseheir.com/", "clicks": 145, "impressions": 2800, "ctr": 0.052, "position": 6.2},
                {"page": "https://coulisseheir.com/services/", "clicks": 62, "impressions": 1100, "ctr": 0.056, "position": 7.8},
                {"page": "https://coulisseheir.com/hair-rescue-treatment-promotion/", "clicks": 38, "impressions": 980, "ctr": 0.039, "position": 9.1},
            ],
            "weak_pages": [
                {"page": "https://coulisseheir.com/team/", "clicks": 4, "impressions": 320, "ctr": 0.013, "position": 8.5},
            ],
            "summary": {
                "total_clicks": 280,
                "total_impressions": 8400,
                "avg_position": 11.3,
            },
        }
