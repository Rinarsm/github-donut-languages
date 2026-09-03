import html
import math
import os

import requests
from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="GitHub Donut Languages",
    version="1.1.0",
    description=(
        "Dynamic GitHub top languages donut card "
        "with customizable colors, themes, filters, and layout."
    ),
)


# =========================================================
# CACHE
# =========================================================

# Data disimpan maksimal 30 menit.
# Maksimal 200 kombinasi username/config.
language_cache = TTLCache(
    maxsize=200,
    ttl=1800,
)


# =========================================================
# THEMES
# =========================================================

THEMES = {
    "purple": {
        "background": "#141321",
        "title": "#A855F7",
        "text": "#03D8F3",
        "ring": "#242238",
        "border": "#2D2942",
        "colors": [
            "#5B21B6",
            "#7C3AED",
            "#8B5CF6",
            "#A78BFA",
            "#D8B4FE",
            "#E9D5FF",
        ],
    },

    "midnight": {
        "background": "#0D1117",
        "title": "#58A6FF",
        "text": "#C9D1D9",
        "ring": "#21262D",
        "border": "#30363D",
        "colors": [
            "#1F6FEB",
            "#388BFD",
            "#58A6FF",
            "#79C0FF",
            "#A5D6FF",
            "#D2A8FF",
        ],
    },

    "rose": {
        "background": "#160D14",
        "title": "#FB7185",
        "text": "#FBCFE8",
        "ring": "#2E1628",
        "border": "#4A1D3A",
        "colors": [
            "#9F1239",
            "#BE123C",
            "#E11D48",
            "#FB7185",
            "#FDA4AF",
            "#FECDD3",
        ],
    },

    "ocean": {
        "background": "#071A21",
        "title": "#22D3EE",
        "text": "#A5F3FC",
        "ring": "#12333D",
        "border": "#164E63",
        "colors": [
            "#155E75",
            "#0891B2",
            "#06B6D4",
            "#22D3EE",
            "#67E8F9",
            "#A5F3FC",
        ],
    },
}


# =========================================================
# HELPERS
# =========================================================

def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-donut-languages",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    return headers


def clean_hex(value: str, default: str):
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


def parse_colors(value: str, default_colors):
    if not value:
        return default_colors

    result = []

    for item in value.split(","):
        color = clean_hex(item, "")

        if color:
            result.append(color)

    return result or default_colors


def parse_excluded_languages(value: str):
    if not value:
        return set()

    return {
        item.strip().lower()
        for item in value.split(",")
        if item.strip()
    }


def get_theme(name: str):
    name = name.lower().strip()

    if name not in THEMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown theme '{name}'. "
                f"Available themes: {', '.join(THEMES.keys())}"
            ),
        )

    return THEMES[name]


# =========================================================
# GITHUB DATA
# =========================================================

def get_repositories(
    username: str,
    include_forks: bool = False,
):
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

        if response.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail=(
                    "GitHub API rate limit reached "
                    "or access was denied."
                ),
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

    filtered = []

    for repo in repositories:
        if repo.get("archived"):
            continue

        if repo.get("fork") and not include_forks:
            continue

        filtered.append(repo)

    return filtered


def get_language_totals(
    username: str,
    include_forks: bool = False,
):
    cache_key = (
        username.lower(),
        include_forks,
    )

    if cache_key in language_cache:
        return language_cache[cache_key]

    repositories = get_repositories(
        username=username,
        include_forks=include_forks,
    )

    totals = {}

    for repo in repositories:
        response = requests.get(
            repo["languages_url"],
            headers=github_headers(),
            timeout=20,
        )

        if response.status_code != 200:
            continue

        data = response.json()

        for language, byte_count in data.items():
            totals[language] = (
                totals.get(language, 0)
                + byte_count
            )

    language_cache[cache_key] = totals

    return totals


# =========================================================
# LANGUAGE PROCESSING
# =========================================================

def prepare_languages(
    data: dict,
    top: int,
    exclude: set,
    hide_other: bool,
):
    filtered = {
        language: value
        for language, value in data.items()
        if language.lower() not in exclude
    }

    if not filtered:
        return []

    sorted_languages = sorted(
        filtered.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    grand_total = sum(filtered.values())

    visible = sorted_languages[:top]
    hidden = sorted_languages[top:]

    result = []

    for language, value in visible:
        result.append(
            {
                "name": language,
                "value": value,
                "percentage": (
                    value / grand_total * 100
                ),
            }
        )

    other_total = sum(
        value
        for _, value in hidden
    )

    if (
        other_total > 0
        and not hide_other
    ):
        result.append(
            {
                "name": "Other",
                "value": other_total,
                "percentage": (
                    other_total
                    / grand_total
                    * 100
                ),
            }
        )

    return result


# =========================================================
# SVG GENERATOR
# =========================================================

def build_svg(
    username: str,
    languages: list,
    colors: list,
    background: str,
    title_color: str,
    text_color: str,
    ring_color: str,
    border_color: str,
    custom_title: str,
    donut_width: int,
    gap: float,
    show_percent: bool,
):
    width = 460
    height = 210

    cx = 345
    cy = 110
    radius = 52

    circumference = (
        2
        * math.pi
        * radius
    )

    if custom_title:
        title = html.escape(custom_title)
    else:
        title = html.escape(
            f"{username}'s Top Languages"
        )

    legend = []
    circles = []

    offset = 0.0

    for index, language in enumerate(languages):
        color = colors[
            index % len(colors)
        ]

        percentage = language["percentage"]

        full_length = (
            circumference
            * percentage
            / 100
        )

        visible_length = max(
            full_length - gap,
            0,
        )

        circles.append(
            f"""
            <circle
                cx="{cx}"
                cy="{cy}"
                r="{radius}"
                fill="none"
                stroke="{color}"
                stroke-width="{donut_width}"
                stroke-linecap="butt"
                stroke-dasharray="
                    {visible_length:.2f}
                    {circumference - visible_length:.2f}
                "
                stroke-dashoffset="{-offset:.2f}"
                transform="rotate(-90 {cx} {cy})"
            />
            """
        )

        offset += full_length

        y = 60 + (index * 23)

        language_name = html.escape(
            language["name"]
        )

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
                font-family="
                    Segoe UI,
                    Arial,
                    sans-serif
                "
                font-size="12"
            >
                {language_name}
            </text>
            """
        )

        if show_percent:
            legend.append(
                f"""
                <text
                    x="210"
                    y="{y}"
                    text-anchor="end"
                    fill="{text_color}"
                    font-family="
                        Segoe UI,
                        Arial,
                        sans-serif
                    "
                    font-size="11"
                >
                    {percentage:.1f}%
                </text>
                """
            )

    svg = f"""
    <svg
        width="{width}"
        height="{height}"
        viewBox="0 0 {width} {height}"
        xmlns="http://www.w3.org/2000/svg"
        role="img"
        aria-label="{title}"
    >

        <rect
            x="0.5"
            y="0.5"
            width="{width - 1}"
            height="{height - 1}"
            rx="10"
            fill="{background}"
            stroke="{border_color}"
        />

        <text
            x="25"
            y="30"
            fill="{title_color}"
            font-family="
                Segoe UI,
                Arial,
                sans-serif
            "
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
            stroke="{ring_color}"
            stroke-width="{donut_width}"
        />

        {''.join(circles)}

    </svg>
    """

    return svg


# =========================================================
# BASIC ENDPOINTS
# =========================================================

@app.get("/")
def home():
    return {
        "project": "GitHub Donut Languages",
        "version": "1.1.0",
        "endpoints": {
            "svg": "/api/languages.svg",
            "json": "/api/languages",
            "themes": "/themes",
            "health": "/health",
        },
        "example": (
            "/api/languages.svg"
            "?username=Rinarsm"
            "&theme=purple"
        ),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.1.0",
        "cache_items": len(language_cache),
    }


@app.get("/themes")
def themes():
    return {
        "themes": {
            name: {
                "background": theme["background"],
                "title": theme["title"],
                "text": theme["text"],
                "colors": theme["colors"],
            }
            for name, theme in THEMES.items()
        }
    }


# =========================================================
# JSON ENDPOINT
# =========================================================

@app.get("/api/languages")
def languages_json(
    username: str,
    top: int = Query(
        default=5,
        ge=1,
        le=10,
    ),
    exclude: str = "",
    include_forks: bool = False,
    hide_other: bool = False,
):
    totals = get_language_totals(
        username=username,
        include_forks=include_forks,
    )

    languages = prepare_languages(
        data=totals,
        top=top,
        exclude=parse_excluded_languages(exclude),
        hide_other=hide_other,
    )

    return {
        "username": username,
        "top": top,
        "include_forks": include_forks,
        "excluded_languages": list(
            parse_excluded_languages(exclude)
        ),
        "languages": languages,
    }


# =========================================================
# SVG ENDPOINT
# =========================================================

@app.get("/api/languages.svg")
def languages_svg(
    username: str,

    theme: str = "purple",

    top: int = Query(
        default=5,
        ge=1,
        le=10,
    ),

    exclude: str = "",

    include_forks: bool = False,

    hide_other: bool = False,

    colors: str = "",

    bg: str = "",

    title_color: str = "",

    text_color: str = "",

    border_color: str = "",

    ring_color: str = "",

    title: str = "",

    donut_width: int = Query(
        default=20,
        ge=8,
        le=35,
    ),

    gap: float = Query(
        default=3,
        ge=0,
        le=12,
    ),

    show_percent: bool = True,
):
    selected_theme = get_theme(theme)

    totals = get_language_totals(
        username=username,
        include_forks=include_forks,
    )

    languages = prepare_languages(
        data=totals,
        top=top,
        exclude=parse_excluded_languages(exclude),
        hide_other=hide_other,
    )

    if not languages:
        raise HTTPException(
            status_code=404,
            detail="No language data found.",
        )

    final_colors = parse_colors(
        colors,
        selected_theme["colors"],
    )

    svg = build_svg(
        username=username,
        languages=languages,
        colors=final_colors,
        background=clean_hex(
            bg,
            selected_theme["background"],
        ),
        title_color=clean_hex(
            title_color,
            selected_theme["title"],
        ),
        text_color=clean_hex(
            text_color,
            selected_theme["text"],
        ),
        ring_color=clean_hex(
            ring_color,
            selected_theme["ring"],
        ),
        border_color=clean_hex(
            border_color,
            selected_theme["border"],
        ),
        custom_title=title,
        donut_width=donut_width,
        gap=gap,
        show_percent=show_percent,
    )

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": (
                "public, max-age=1800"
            ),
        },
    )