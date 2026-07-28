import streamlit as st
import theme

def get_logo_html(source: str, size: int = 24) -> str:
    """Returns HTML for an SVG logo based on the data source name, respecting the house theme."""
    source = source.lower()
    
    # SVG Strings (Mocked minimalist SVGs in house colors)
    # Using theme.COLORS for styling
    logos = {
        "gdelt": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{theme.COLORS["blue"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>',
        "reddit": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{theme.COLORS["amber"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
        "polymarket": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{theme.COLORS["green"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>',
        "reuters": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{theme.COLORS["purple"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>'
    }
    
    default_logo = f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{theme.COLORS["muted"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
    
    return logos.get(source, default_logo)

def render_sources_badge(sources: list[str]) -> str:
    """Returns HTML for a row of logos for the given sources."""
    html = '<div style="display: flex; gap: 8px; align-items: center; margin-top: 4px;">'
    for src in sources:
        html += f'<span title="{src.capitalize()}">{get_logo_html(src, 16)}</span>'
    html += '</div>'
    return html