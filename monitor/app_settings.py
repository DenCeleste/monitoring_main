# app_settings.py
import json
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

CONFIG_PATH = Path("sites.json")


def load_sites() -> list[dict]:
    if not CONFIG_PATH.exists():
        return []
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_sites(sites: list[dict]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(sites, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def new_id(url: str) -> str:
    return urlparse(url).netloc.replace(".", "_") or "site"


def render_icon(icon: str, size: int = 32):
    """Emoji или URL — рендерим одинаково удобно."""
    if icon.startswith("http"):
        st.image(icon, width=size)
    else:
        st.markdown(
            f"<span style='font-size:{size}px'>{icon}</span>",
            unsafe_allow_html=True,
        )


def guess_favicon(url: str) -> str:
    domain = urlparse(url).netloc
    if not domain:
        return "🌐"
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico"


st.set_page_config(page_title="Настройки монитора", page_icon="🛠️")
st.title("🛠️ Настройки сайтов")

sites = load_sites()

tab_list, tab_add = st.tabs(["📋 Список сайтов", "➕ Добавить сайт"])


# ---------- Редактирование существующих ----------
with tab_list:
    if not sites:
        st.info("Пока нет ни одного сайта. Добавьте на вкладке «Добавить сайт».")

    for idx, site in enumerate(sites):
        header = f"{site.get('icon', '🌐')} {site['name']} — {site['url']}"
        with st.expander(header):
            col_icon, col_form = st.columns([1, 4])
            with col_icon:
                render_icon(site.get("icon", "🌐"), size=48)
            with col_form:
                name = st.text_input("Название", site["name"], key=f"name_{idx}")
                url = st.text_input("URL", site["url"], key=f"url_{idx}")
                icon = st.text_input(
                    "Иконка (emoji или URL)",
                    site.get("icon", "🌐"),
                    key=f"icon_{idx}",
                )
                if st.button("🔍 Подобрать favicon", key=f"fav_{idx}"):
                    st.session_state[f"icon_{idx}"] = guess_favicon(url)
                    st.rerun()
                description = st.text_area(
                    "Описание", site.get("description", ""), key=f"desc_{idx}"
                )
                group = st.text_input(
                    "Группа", site.get("group", "default"), key=f"grp_{idx}"
                )

            c1, c2, c3 = st.columns(3)
            with c1:
                interval = st.number_input(
                    "Интервал, сек",
                    min_value=10,
                    value=int(site.get("interval_sec", 300)),
                    step=10,
                    key=f"int_{idx}",
                )
            with c2:
                timeout = st.number_input(
                    "Таймаут, сек",
                    min_value=1.0,
                    value=float(site.get("timeout_sec", 10.0)),
                    step=1.0,
                    key=f"to_{idx}",
                )
            with c3:
                method = st.selectbox(
                    "Метод",
                    ["GET", "HEAD"],
                    index=["GET", "HEAD"].index(site.get("method", "GET")),
                    key=f"m_{idx}",
                )

            expected = st.text_input(
                "Ожидаемый статус (пусто = любой 2xx/3xx)",
                "" if site.get("expected_status") is None
                else str(site["expected_status"]),
                key=f"exp_{idx}",
            )
            keyword = st.text_input(
                "Ключевое слово в ответе (опционально)",
                site.get("keyword", ""),
                key=f"kw_{idx}",
            )
            enabled = st.checkbox(
                "Включён", site.get("enabled", True), key=f"en_{idx}"
            )

            col_save, col_del = st.columns(2)
            with col_save:
                if st.button("💾 Сохранить", key=f"save_{idx}", type="primary"):
                    sites[idx] = {
                        "id": site.get("id") or new_id(url),
                        "name": name,
                        "url": url,
                        "icon": icon or "🌐",
                        "description": description,
                        "group": group,
                        "enabled": enabled,
                        "interval_sec": int(interval),
                        "timeout_sec": float(timeout),
                        "method": method,
                        "expected_status": int(expected)
                        if expected.strip().isdigit() else None,
                        "keyword": keyword,
                    }
                    save_sites(sites)
                    st.success("Сохранено")
                    st.rerun()
            with col_del:
                if st.button("🗑 Удалить", key=f"del_{idx}"):
                    sites.pop(idx)
                    save_sites(sites)
                    st.rerun()


# ---------- Добавление нового ----------
with tab_add:
    with st.form("add_site", clear_on_submit=True):
        name = st.text_input("Название", "")
        url = st.text_input("URL", "https://")
        icon = st.text_input("Иконка (emoji или URL)", "🌐")
        description = st.text_area("Описание", "")
        group = st.text_input("Группа", "default")

        c1, c2, c3 = st.columns(3)
        with c1:
            interval = st.number_input("Интервал, сек", min_value=10, value=300, step=10)
        with c2:
            timeout = st.number_input("Таймаут, сек", min_value=1.0, value=10.0, step=1.0)
        with c3:
            method = st.selectbox("Метод", ["GET", "HEAD"])

        expected = st.text_input("Ожидаемый статус (пусто = любой 2xx/3xx)", "")
        keyword = st.text_input("Ключевое слово в ответе (опционально)", "")
        enabled = st.checkbox("Включён", True)

        submitted = st.form_submit_button("➕ Добавить")
        if submitted:
            if not name or not url.startswith("http"):
                st.error("Нужны название и корректный URL (http/https)")
            else:
                sites.append({
                    "id": new_id(url),
                    "name": name,
                    "url": url,
                    "icon": icon or "🌐",
                    "description": description,
                    "group": group,
                    "enabled": enabled,
                    "interval_sec": int(interval),
                    "timeout_sec": float(timeout),
                    "method": method,
                    "expected_status": int(expected)
                    if expected.strip().isdigit() else None,
                    "keyword": keyword,
                })
                save_sites(sites)
                st.success(f"Сайт «{name}» добавлен")
                st.rerun()
                #streamlit run app_settings.py