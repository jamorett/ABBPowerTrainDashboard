import streamlit as st
import datetime
import hashlib

def init_notification_state():
    """Inicializar session state para el sistema de alertas IA."""
    if "ia_notifications" not in st.session_state:
        st.session_state.ia_notifications = []
    if "dismissed_ids" not in st.session_state:
        st.session_state.dismissed_ids = set()
    if "threshold_breach_start" not in st.session_state:
        st.session_state.threshold_breach_start = {}  # key: f"{asset_id}_{kpi_name}", value: datetime


def _make_id(asset_id, notif_type, message):
    """Generar un ID estable para deduplicar alertas del mismo activo+tipo."""
    raw = f"{asset_id}_{notif_type}_{message[:60]}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def add_notification(asset_id, asset_name, notif_type, message, severity="Warning"):
    """
    Añadir una notificacion IA al log. Deduplica por asset+tipo+prefijo de mensaje.
    Las notificaciones de ABB NO van aqui — solo las diagnosticadas localmente por nuestro motor.
    """
    nid = _make_id(asset_id, notif_type, message)
    existing_ids = {n["id"] for n in st.session_state.ia_notifications}
    if nid in existing_ids:
        return  # Ya registrada, no duplicar

    st.session_state.ia_notifications.append({
        "id": nid,
        "asset_id": asset_id,
        "asset_name": asset_name,
        "type": notif_type,
        "message": message,
        "severity": severity,
        "timestamp": datetime.datetime.now().strftime("%H:%M | %d/%m")
    })


def check_persistent_breach(asset_id, asset_name, kpis, threshold_hours=0.5):
    """
    Detectar KPIs que llevan más de 'threshold_hours' horas en estado critico.
    Genera una notificacion de umbral sostenido si supera el tiempo.
    """
    try:
        from translator import translate_kpi_name, translate_condition
    except ImportError:
        def translate_kpi_name(x): return x
        def translate_condition(x): return x

    now = datetime.datetime.now()
    for k in kpis:
        kpi_name = k.get("name", "")
        cond = k.get("currentCondition", "")

        if cond in ["Alarm", "Error", "Poor", "Bad", "Critical"]:
            key = f"{asset_id}_{kpi_name}"
            if key not in st.session_state.threshold_breach_start:
                st.session_state.threshold_breach_start[key] = now
            else:
                elapsed = (now - st.session_state.threshold_breach_start[key]).total_seconds() / 3600.0
                if elapsed >= threshold_hours:
                    msg = (f"El KPI '{translate_kpi_name(kpi_name)}' lleva "
                           f"{elapsed:.1f}h en estado '{translate_condition(cond)}'. "
                           f"Revisar urgentemente.")
                    add_notification(asset_id, asset_name, "Umbral Sostenido", msg, "Error")
        else:
            # Condición mejoró — resetear el reloj
            key = f"{asset_id}_{kpi_name}"
            st.session_state.threshold_breach_start.pop(key, None)


def render_floating_notifications(asset_id=None):
    """
    Renderizar notificaciones flotantes en la parte superior del Kiosko.
    Si se pasa asset_id, solo muestra las alertas de ese equipo.
    """
    active = [n for n in st.session_state.ia_notifications
              if n["id"] not in st.session_state.dismissed_ids]
    if asset_id:
        active = [n for n in active if n["asset_id"] == asset_id]
    if not active:
        return

    import streamlit.components.v1 as components
    import json

    # Pasamos TODAS las alertas activas — JS filtrará las descartadas
    # y mostrará las primeras 4 que no estén en sessionStorage.
    notifs_data = []
    for n in active:
        notifs_data.append({
            "id":         n["id"],
            "type":       n["type"],
            "asset_name": n["asset_name"],
            "message":    n["message"][:100] + ("…" if len(n["message"]) > 100 else ""),
            "severity":   n["severity"],
            "timestamp":  n["timestamp"],
            "icon":       "🔴" if n["severity"] == "Error" else "🟡",
            "css_class":  "ia-err" if n["severity"] == "Error" else "ia-warn",
        })
    notifs_json = json.dumps(notifs_data, ensure_ascii=False)

    js = f"""
    <script>
    (function() {{
        var p  = window.parent;
        var pd = p.document;

        /* ── 1. Limpiar contenedor anterior para re-render limpio ── */
        var old = pd.getElementById('ia-notif-root');
        if (old) old.remove();

        /* ── 2. Inyectar CSS una sola vez ── */
        if (!pd.getElementById('ia-notif-style')) {{
            var s = pd.createElement('style');
            s.id = 'ia-notif-style';
            s.textContent = `
                #ia-notif-root {{
                    position: fixed; top: 70px; right: 18px; z-index: 9999;
                    display: flex; flex-direction: column; gap: 10px;
                    max-width: 340px;
                    font-family: 'Inter', 'Segoe UI', sans-serif;
                    pointer-events: none;
                }}
                .ia-notif-card {{
                    border-radius: 12px; padding: 12px 16px;
                    backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
                    animation: iaSlideIn 0.4s cubic-bezier(0.22,1,0.36,1);
                    pointer-events: auto;
                }}
                .ia-notif-card.ia-warn {{
                    background: linear-gradient(135deg,rgba(255,243,200,.97),rgba(255,230,140,.97));
                    border: 1px solid rgba(210,150,0,.6);
                    box-shadow: 0 6px 24px rgba(200,130,0,.20);
                }}
                .ia-notif-card.ia-err {{
                    background: linear-gradient(135deg,rgba(255,220,220,.97),rgba(255,195,195,.97));
                    border: 1px solid rgba(200,60,60,.6);
                    box-shadow: 0 6px 24px rgba(200,40,40,.20);
                }}
                .ia-notif-hdr {{
                    display:flex; justify-content:space-between;
                    align-items:flex-start; margin-bottom:3px;
                }}
                .ia-notif-label {{
                    font-size:.67rem; font-weight:700;
                    letter-spacing:.8px; text-transform:uppercase; color:#333;
                }}
                .ia-notif-asset  {{ font-size:.90rem; font-weight:700; color:#111; margin-bottom:4px; }}
                .ia-notif-msg    {{ font-size:.79rem; color:#333; line-height:1.45; }}
                .ia-notif-time   {{ font-size:.67rem; color:#444; margin-top:5px; }}
                .ia-close-btn {{
                    background:none; border:none; cursor:pointer;
                    font-size:.92rem; color:#777; padding:0 0 0 10px;
                    line-height:1; opacity:.65;
                    transition: opacity .15s, color .15s;
                }}
                .ia-close-btn:hover {{ opacity:1; color:#222; }}
                @keyframes iaSlideIn {{
                    from {{ opacity:0; transform:translateX(24px); }}
                    to   {{ opacity:1; transform:translateX(0); }}
                }}
            `;
            pd.head.appendChild(s);
        }}

        /* ── 3. Función de descarte global ── */
        p.iaClose = function(nid) {{
            sessionStorage.setItem('ia_d_' + nid, '1');
            var el = pd.getElementById('ia-card-' + nid);
            if (el) el.style.display = 'none';
        }};

        /* ── 4. Construir y añadir cards al DOM del parent ── */
        var notifs  = {notifs_json};
        var root    = pd.createElement('div');
        root.id     = 'ia-notif-root';
        var shown   = 0;   // cards visibles añadidas
        var hidden  = 0;   // descartadas omitidas

        notifs.forEach(function(n) {{
            /* saltar si ya fue descartado en esta sesión del navegador */
            if (sessionStorage.getItem('ia_d_' + n.id)) {{ hidden++; return; }}

            /* solo mostrar las primeras 4 no descartadas */
            if (shown >= 4) {{ hidden++; return; }}
            shown++;

            var card = pd.createElement('div');
            card.className = 'ia-notif-card ' + n.css_class;
            card.id = 'ia-card-' + n.id;

            /* header: label + botón ✕ */
            var hdr = pd.createElement('div');
            hdr.className = 'ia-notif-hdr';

            var lbl = pd.createElement('div');
            lbl.className   = 'ia-notif-label';
            lbl.textContent = n.icon + ' ' + n.type;

            var btn = pd.createElement('button');
            btn.className   = 'ia-close-btn';
            btn.title       = 'Descartar';
            btn.textContent = '✕';
            /* listener con closure correcto — no atributo onclick */
            btn.addEventListener('click', (function(nid) {{
                return function(e) {{ e.stopPropagation(); p.iaClose(nid); }};
            }})(n.id));

            hdr.appendChild(lbl);
            hdr.appendChild(btn);

            var asset = pd.createElement('div');
            asset.className   = 'ia-notif-asset';
            asset.textContent = '📌 ' + n.asset_name;

            var msg = pd.createElement('div');
            msg.className   = 'ia-notif-msg';
            msg.textContent = n.message;

            var time = pd.createElement('div');
            time.className   = 'ia-notif-time';
            time.textContent = '🕐 ' + n.timestamp;

            card.appendChild(hdr);
            card.appendChild(asset);
            card.appendChild(msg);
            card.appendChild(time);
            root.appendChild(card);
        }});

        if (hidden > 0) {{
            var more = pd.createElement('div');
            more.style.cssText = 'color:#444;font-size:.76rem;background:rgba(240,240,240,.92);border-radius:8px;padding:6px 10px;pointer-events:auto;';
            more.textContent   = '+' + hidden + ' alertas más — ver historial abajo';
            root.appendChild(more);
        }}

        pd.body.appendChild(root);
    }})();
    </script>
    """
    components.html(js, height=0)


def render_alert_history_panel():
    """
    Panel plegable (expander) con el historial completo de todas las alertas IA de la sesión.
    Muestra activas (con boton dismiss) y descartadas (en gris). Incluye botón de limpieza total.
    """
    all_n = st.session_state.ia_notifications
    dismissed = st.session_state.dismissed_ids
    active_n = [n for n in all_n if n["id"] not in dismissed]
    disc_n = [n for n in all_n if n["id"] in dismissed]

    label = f"🔔 Centro de Alertas IA — {len(active_n)} activa(s) | {len(all_n)} en historial"
    with st.expander(label, expanded=False):
        if not all_n:
            st.info("No hay alertas IA registradas en esta sesión.")
            return

        # ---- Botones de descarte rápido (dentro del expander = aislados del layout) ----
        if active_n:
            bd1, bd2, _ = st.columns([2, 2, 8])
            if bd1.button("✕ Última alerta", key="dis_last", use_container_width=True):
                st.session_state.dismissed_ids.add(active_n[-1]["id"])
                st.rerun()
            if bd2.button("✕ Descartar todas", key="dis_all", use_container_width=True):
                for n in active_n:
                    st.session_state.dismissed_ids.add(n["id"])
                st.rerun()
            st.markdown("---")

        if active_n:
            st.markdown("#### 🔴 Alertas Activas")
            for n in reversed(active_n):
                color = "#c0392b" if n["severity"] == "Error" else "#e67e00"
                c1, c2 = st.columns([11, 1])
                c1.markdown(
                    f"<div style='border-left:3px solid {color}; padding-left:10px; margin-bottom:10px;'>"
                    f"<b style='color:{color}'>{n['type']}</b>"
                    f" &nbsp;·&nbsp; <b style='color:#111'>{n['asset_name']}</b>"
                    f" <span style='color:#777; font-size:0.78em'>{n['timestamp']}</span><br>"
                    f"<span style='font-size:0.88em; color:#333'>{n['message']}</span></div>",
                    unsafe_allow_html=True
                )
                if c2.button("✕", key=f"hdis_{n['id']}", help="Descartar"):
                    st.session_state.dismissed_ids.add(n["id"])
                    st.rerun()

        if disc_n:
            st.markdown("---")
            st.markdown(f"<small style='color:#888'>⚫ Descartadas ({len(disc_n)})</small>",
                        unsafe_allow_html=True)
            for n in reversed(disc_n[-6:]):
                st.markdown(
                    f"<span style='color:#999; font-size:0.82em'>"
                    f"~~{n['asset_name']} — {n['type']}~~ "
                    f"<span style='color:#aaa'>{n['timestamp']}</span></span>",
                    unsafe_allow_html=True
                )

        st.markdown("---")
        if st.button("🗑️ Limpiar historial completo", key="clear_all_ia"):
            st.session_state.ia_notifications = []
            st.session_state.dismissed_ids = set()
            st.rerun()
