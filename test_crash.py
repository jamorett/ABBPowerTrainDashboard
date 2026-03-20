import streamlit as st
from unittest.mock import MagicMock

# Configurar el estado de streamlit simulado
st.session_state.asset_statuses = {}
st.session_state.kiosk_active = True
st.session_state.kiosk_index = 0
st.session_state.kiosk_paused = False

import app
try:
    print("Iniciando render_kiosk_mode...")
    app.render_kiosk_mode()
    print("Render Kiosk exitoso!")
    
    print("Iniciando render_manual_mode...")
    app.render_manual_mode()
    print("Render Manual exitoso!")
except Exception as e:
    import traceback
    traceback.print_exc()
