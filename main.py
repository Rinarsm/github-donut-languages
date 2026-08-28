import html
import math
import os

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

load_dotenv()

app = FastAPI(
    title="GitHub Donut Languages",
    version="1.0.0",
    description="Dynamic and customizable GitHub top languages donut card.",
)

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DEFAULT_COLORS = [
    "#5B21B6",
    "#7C3AED",
    "#8B5CF6",
    "#A78BFA",
    "#D8B4FE",
    "#E9D5FF",
]


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-donut-languages",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def clean_hex(value: str, default: str) -> str:
    if not value:
        return default

    value = value.strip().replace("#", "")

    if len(value) not in (3, 6):
        return default

    try:
        int(value, 16)
    except ValueError:
        return default

    return f"#{value}"


def parse_colors(value: str):
    if not value:
        return DEFAULT_COLORS

    colors = []

    for color in value.split(","):
        cleaned = clean_hex(color, "")

        if cleaned:
            colors.append(cleaned)

    return colors or DEFAULT_COLORS


def get_repositories(username: str):
    repositories = []

    page = 1

    while True:
        response = requests.get(
            f"{GITHUB_API}/users/{username}/repos",
            headers=github_headers(),
            params={
                "type": "owner",
                "sort": "updated",
                "per_page": 100,
                "page": page,
            },
            timeout=20,
        )

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="GitHub user not found.",
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch GitHub repositories.",
            )

        data = response.json()

        if not data:
            break

        repositories.extend(data)

        if len(data) < 100:
            break

        page += 1

    return [
        repo
        for repo in repositories
        if not repo.get("fork")
        and not repo.get("archived")
    ]


def get_language_totals(username: str):
    repositories = get_repositories(username)

    totals = {}

    for repo in repositories:
        response = requests.get(
            repo["languages_url"],
            headers=github_headers(),
            timeout=20,
        )

        if response.status_code != 200:
            continue

        for language, byte_count in response.json().items():
            totals[language] = totals.get(language, 0) + byte_count

    return totals


def prepare_languages(data: dict, top: int):
    if not data:
        return []

    sorted_languages = sorted(
        data.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    grand_total = sum(data.values())

    visible = sorted_languages[:top]
    hidden = sorted_languages[top:]

    result = []

    for language, value in visible:
        result.append(
            {
                "name": language,
                "value": value,
                "percentage": value / grand_total * 100,
            }
        )

    other_total = sum(value for _, value in hidden)

    if other_total > 0:
        result.append(
            {
                "name": "Other",
                "value": other_total,
                "percentage": other_total / grand_total * 100,
            }
        )

    return result


def build_svg(
    username: str,
    languages: list,
    colors: list,
    background: str,
    title_color: str,
    text_color: str,
):
    width = 460
    height = 200

    cx = 345
    cy = 105
    radius = 52
    stroke_width = 20

    circumference = 2 * math.pi * radius
    segment_gap = 3

    title = html.escape(f"{username}'s Top Languages")

    legend = []
    circles = []

    offset = 0.0

    for index, language in enumerate(languages):
        color = colors[index % len(colors)]

        percentage = language["percentage"]

        full_length = circumference * (percentage / 100)
        visible_length = max(full_length - segment_gap, 0)

        circles.append(
            f"""
            <circle
                cx="{cx}"
                cy="{cy}"
                r="{radius}"
                fill="none"
                stroke="{color}"
                stroke-width="{stroke_width}"
                stroke-dasharray="{visible_length:.2f} {circumference - visible_length:.2f}"
                stroke-dashoffset="{-offset:.2f}"
                transform="rotate(-90 {cx} {cy})"
            />
            """
        )

        offset += full_length

        y = 62 + (index * 23)

        name = html.escape(language["name"])

        legend.append(
            f"""
            <rect
                x="25"
                y="{y - 10}"
                width="10"
                height="10"
                rx="2"
                fill="{color}"
            />

            <text
                x="43"
                y="{y}"
                fill="{text_color}"
                font-family="Segoe UI, Arial, sans-serif"
                font-size="12"
            >
                {name}
            </text>

            <text
                x="205"
                y="{y}"
                text-anchor="end"
                fill="{text_color}"
                font-family="Segoe UI, Arial, sans-serif"
                font-size="11"
            >
                {percentage:.1f}%
            </text>
            """
        )

    return f"""
    <svg
        width="{width}"
        height="{height}"
        viewBox="0 0 {width} {height}"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label="{title}"
    >

        <rect
            width="{width}"
            height="{height}"
            rx="10"
            fill="{background}"
        />

        <text
            x="25"
            y="30"
            fill="{title_color}"
            font-family="Segoe UI, Arial, sans-serif"
            font-size="17"
            font-weight="600"
        >
            {title}
        </text>

        {''.join(legend)}

        <circle
            cx="{cx}"
            cy="{cy}"
            r="{radius}"
            fill="none"
            stroke="#242238"
            stroke-width="{stroke_width}"
        />

        {''.join(circles)}

    </svg>
    """


@app.get("/")
def home():
    return {
        "project": "GitHub Donut Languages",
        "version": "1.0.0",
        "example": (
            "/api/languages.svg?"
            "username=Rinarsm&"
            "colors=5B21B6,7C3AED,8B5CF6,A78BFA,D8B4FE"
        ),
    }


@app.get("/api/languages")
def languages_json(
    username: str,
    top: int = Query(default=5, ge=1, le=10),
):
    totals = get_language_totals(username)

    return {
        "username": username,
        "languages": prepare_languages(totals, top),
    }


@app.get("/api/languages.svg")
def languages_svg(
    username: str,
    top: int = Query(default=5, ge=1, le=10),
    colors: str = "",
    bg: str = "141321",
    title_color: str = "A855F7",
    text_color: str = "03D8F3",
):
    totals = get_language_totals(username)

    languages = prepare_languages(totals, top)

    if not languages:
        raise HTTPException(
            status_code=404,
            detail="No language data found.",
        )

    svg = build_svg(
        username=username,
        languages=languages,
        colors=parse_colors(colors),
        background=clean_hex(bg, "#141321"),
        title_color=clean_hex(title_color, "#A855F7"),
        text_color=clean_hex(text_color, "#03D8F3"),
    )

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=1800",
        },
    )