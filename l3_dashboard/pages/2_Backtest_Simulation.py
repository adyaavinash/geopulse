import streamlit as st
import json
import pandas as pd
import theme

st.set_page_config(page_title="GeoPulse Backtest Simulation", layout="wide", page_icon="📈")
theme.inject()
theme.render_sidebar()

st.markdown(
    f"""
    <div style='margin-bottom: 1.6rem;'>
        <div class='gp-kicker' style='margin-bottom: 8px;'>Historical Backtesting</div>
        <h1 style='margin: 0; padding: 0; font-size: 2.5rem; letter-spacing: -1px; color: {theme.COLORS["ink"]};'>Performance Simulation</h1>
        <div style='color: {theme.COLORS["muted"]}; font-size: 1.1rem; margin-top: 4px; max-width:760px'>Simulated financial performance of trading on the AI's predictive signals versus a passive S&amp;P 500 hold strategy (2000 &ndash; present).</div>
    </div>
    """, unsafe_allow_html=True
)


@st.cache_data
def load_backtest_data():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    try:
        with open(root / "tests/fixtures/mock_backtest.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


data = load_backtest_data()

if data:
    df = pd.DataFrame({
        'Date': pd.to_datetime(data['dates']),
        'AI Portfolio': data['ai_portfolio'],
        'S&P 500 Baseline': data['sp500_baseline']
    })
    df.set_index('Date', inplace=True)

    final_ai = df['AI Portfolio'].iloc[-1]
    final_sp500 = df['S&P 500 Baseline'].iloc[-1]
    alpha = final_ai - final_sp500
    alpha_pct = (final_ai / final_sp500 - 1) * 100 if final_sp500 else 0

    # Summary metrics — now with sparklines drawn from the actual series
    ai_spark = df['AI Portfolio'].iloc[:: max(1, len(df) // 40)].tolist()
    sp_spark = df['S&P 500 Baseline'].iloc[:: max(1, len(df) // 40)].tolist()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(theme.stat_card(
            "AI Portfolio (Simulated)", f"${final_ai:,.0f}", "End value · $10,000 start",
            "muted", spark_values=ai_spark, spark_tone="amber", accent=True,
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(theme.stat_card(
            "S&P 500 (Baseline)", f"${final_sp500:,.0f}", "End value · passive hold",
            "muted", spark_values=sp_spark, spark_tone="muted",
        ), unsafe_allow_html=True)
    with c3:
        st.markdown(theme.stat_card(
            "Alpha Generated", f"+${alpha:,.0f}", f"+{alpha_pct:.1f}% vs market (24y)",
            "green",
        ), unsafe_allow_html=True)

    st.write("")

    # --------------------------------------------------------------------- #
    # Equity curve — dependency-free SVG line chart (no Altair/rpds risk)
    # --------------------------------------------------------------------- #
    st.markdown(
        theme.section_header("Equity Curve", "AI Portfolio vs. S&P 500",
                              "Growth of a simulated $10,000 position, rebased at inception."),
        unsafe_allow_html=True,
    )

    # Downsample for a crisp, fast-rendering SVG regardless of history length
    stride = max(1, len(df) // 180)
    plot_df = df.iloc[:: stride]
    x_labels = plot_df.index.strftime('%Y').tolist()

    chart_html = theme.line_chart_svg(
        x_labels,
        {
            "AI Portfolio": {"values": plot_df['AI Portfolio'].tolist(), "tone": "amber"},
            "S&P 500 Baseline": {"values": plot_df['S&P 500 Baseline'].tolist(), "tone": "muted"},
        },
        height=340,
    )
    st.markdown(f"<div class='gp-card'>{chart_html}</div>", unsafe_allow_html=True)

    st.caption("Decision-support simulation only — not investment advice. Past performance of a simulated strategy does not guarantee future results.")

    with st.expander("Underlying data"):
        st.markdown(
            df.to_html(float_format=lambda x: f"${x:,.2f}", classes="gp-table", border=0), 
            unsafe_allow_html=True
        )

else:
    st.warning("No backtest data available.")