"""
Componente Streamlit: botão "segure para gravar" — enquanto pressionado grava áudio, ao soltar envia para transcrição.
"""
import os
import streamlit.components.v1 as components

_RELEASE = True
_COMPONENT_NAME = "hold_to_record"

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
_component_func = components.declare_component(
    _COMPONENT_NAME,
    path=frontend_dir,
)


def hold_to_record_button(key=None):
    """
    Renderiza um botão que grava áudio enquanto pressionado e envia ao soltar.
    Retorna None até o usuário soltar o botão; então retorna um dict com:
    - "b64": str (áudio em base64) ou
    - "error": str (ex.: "permission_denied")
    """
    value = _component_func(key=key)
    return value
