import streamlit as st
import datetime
import re
from typing import Dict, List, Optional
from generator import (
    list_templates, get_model_defaults,
    render_device, create_zip_from_dict, safe_filename
)

MODELS = ["3903", "3916", "3926", "3928"]

PORT_RANGES = {
    "3903": [str(i) for i in range(1, 4)],
    "3916": [str(i) for i in range(1, 7)],
    "3928": [str(i) for i in range(1, 13)],
    "3926": [f"1.{i}" for i in range(1, 9)]
}


def build_device_from_inputs(inputs: Dict) -> Dict:
    # Normalize and convert common fields
    dev = {
        "hostname": inputs["hostname"],
        "model": inputs["model"],
        "backhaul": inputs["backhaul"],
        "tacacs_servers": [s for s in [inputs.get("tacacs_server_1"), inputs.get("tacacs_server_2")] if s],
        "tacacs_secret": inputs.get("tacacs_secret"),
        "license_keys": inputs.get("license_keys"),
        "ntp_servers": inputs.get("ntp_servers", []),
        "syslog_collectors": [{"addr": s, "severity": "emergency,alert,error,warning,notice,info,debug"} for s in inputs.get("syslog_collectors", [])],
        "_generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z",
    }

    agg_enabled = inputs.get("aggregation_enabled", False)
    dev["aggregation_enabled"] = bool(agg_enabled)

    if agg_enabled:
        # handle single aggregation
        if inputs["backhaul"] == "single":
            dev["aggregation_name"] = inputs.get("aggregation_name") or None
            dev["aggregation_members"] = inputs.get("single_port") or []
            dev["single_ip"] = f"{inputs['single_ip'].strip()}/{inputs['single_prefix']}" if inputs.get("single_ip") else None
            dev["single_vlan"] = int(inputs["single_vlan"]) if inputs.get("single_vlan") else None
            dev["single_if_name"] = inputs.get("single_if_name") or (f"Agg_{dev['aggregation_members'][0]}" if dev["aggregation_members"] else None)
            dev["single_mtu"] = int(inputs["single_mtu"]) if inputs.get("single_mtu") else None
            dev["aggregations"] = [{"name": dev["aggregation_name"], "members": dev["aggregation_members"]}]
        else:
            # dual aggregation
            primary_members = inputs.get("primary_port") or []
            secondary_members = inputs.get("secondary_port") or []
            dev.update({
                "primary_ip": f"{inputs['primary_ip'].strip()}/{inputs['primary_prefix']}" if inputs.get("primary_ip") else None,
                "primary_vlan": int(inputs["primary_vlan"]) if inputs.get("primary_vlan") else None,
                "primary_if_name": inputs.get("primary_if_name"),
                "primary_mtu": int(inputs["primary_mtu"]) if inputs.get("primary_mtu") else None,
                "secondary_ip": f"{inputs['secondary_ip'].strip()}/{inputs['secondary_prefix']}" if inputs.get("secondary_ip") else None,
                "secondary_vlan": int(inputs["secondary_vlan"]) if inputs.get("secondary_vlan") else None,
                "secondary_if_name": inputs.get("secondary_if_name"),
                "secondary_mtu": int(inputs["secondary_mtu"]) if inputs.get("secondary_mtu") else None,
                "aggregations": [
                    {"name": inputs.get("primary_agg_name") or None, "members": primary_members},
                    {"name": inputs.get("secondary_agg_name") or None, "members": secondary_members},
                ],
            })
    else:
        # no aggregation: set ports/ips directly based on backhaul
        if inputs["backhaul"] == "single":
            dev["single_port"] = inputs.get("single_port")
            dev["single_ip"] = f"{inputs['single_ip'].strip()}/{inputs['single_prefix']}" if inputs.get("single_ip") else None
            dev["single_vlan"] = int(inputs["single_vlan"]) if inputs.get("single_vlan") else None
            dev["single_if_name"] = inputs.get("single_if_name")
            dev["single_mtu"] = int(inputs["single_mtu"]) if inputs.get("single_mtu") else None
        else:
            dev["primary_port"] = inputs.get("primary_port")
            dev["primary_ip"] = f"{inputs['primary_ip'].strip()}/{inputs['primary_prefix']}" if inputs.get("primary_ip") else None
            dev["primary_vlan"] = int(inputs["primary_vlan"]) if inputs.get("primary_vlan") else None
            dev["primary_if_name"] = inputs.get("primary_if_name")
            dev["primary_mtu"] = int(inputs["primary_mtu"]) if inputs.get("primary_mtu") else None

            dev["secondary_port"] = inputs.get("secondary_port")
            dev["secondary_ip"] = f"{inputs['secondary_ip'].strip()}/{inputs['secondary_prefix']}" if inputs.get("secondary_ip") else None
            dev["secondary_vlan"] = int(inputs["secondary_vlan"]) if inputs.get("secondary_vlan") else None
            dev["secondary_if_name"] = inputs.get("secondary_if_name")
            dev["secondary_mtu"] = int(inputs["secondary_mtu"]) if inputs.get("secondary_mtu") else None

    # optional fields
    if int(inputs["model"]) > 3903 and inputs.get("loopback_ip"):
        dev["loopback_ip"] = inputs["loopback_ip"]
    if inputs["model"] == "3903" and inputs.get("gateway"):
        dev["gateway"] = inputs["gateway"]

    return dev


st.set_page_config(page_title="CIENA CONFIG - UPDATED UI", layout="wide")
st.title("CIENA COMMISSIONING CONFIG GENERATOR")

st.sidebar.header("OPTIONS")
available_templates = list_templates()
st.sidebar.markdown("TEMPLATES DETECTED:")
if available_templates:
    for t in available_templates:
        st.sidebar.markdown(f"- `{t}`")
else:
    st.sidebar.info("NO TEMPLATES FOUND IN ./templates")

st.sidebar.markdown("---")
append_ts = st.sidebar.checkbox("APPEND TIMESTAMP TO FILENAME", value=True)

st.header("DEVICE INPUT (SINGLE HOSTNAME)")
col1, col2 = st.columns(2)

with col1:
    hostname = st.text_input("HOSTNAME (SINGLE DEVICE)", value="CIENA-01").strip()
    model = st.selectbox("MODEL", MODELS)
    backhaul_options = ["single"] if model == "3903" else ["single", "dual"]
    backhaul = st.selectbox("BACKHAUL TYPE", backhaul_options, index=0)

    col3, col4 = st.columns(2)
    with col3:
        tacacs_server_1 = st.text_input("TACACS SERVER 1 (IP)", value="10.0.141.210")
    with col4:
        tacacs_server_2 = st.text_input("TACACS SERVER 2 (IP)", value="10.0.141.211")

    model_defaults = get_model_defaults(model)
    tacacs_secret = st.text_input("TACACS SECRET", value=model_defaults.get("tacacs_secret"))
    license_keys_text = st.text_area("LICENSE KEYS — 1 PER LINE", value="\n".join(model_defaults.get("license_keys", [])), height=100)

with col2:
    # defaults for UI
    aggregation_enabled = False
    aggregation_name = ""
    available_ports = PORT_RANGES[model]
    # single vs dual UI blocks (keeps same fields as before but collects into a dict later)
    if backhaul == "single":
        st.subheader("SINGLE BACKHAUL")
        if model != "3903":
            aggregation_enabled = st.checkbox("ENABLE AGGREGATION", value=False)
        else:
            aggregation_enabled = False

        if aggregation_enabled:
            aggregation_name = st.text_input("AGGREGATION NAME", value="Agg_1")
            single_port = st.multiselect("AGG MEMBER PORTS (select one or more)", options=available_ports, default=available_ports[:1], key="single_agg_members")
            single_ip = st.text_input("AGG BACKHAUL IP (NO PREFIX)", value="")
            single_prefix = st.selectbox("AGG BACKHAUL PREFIX (CIDR)", ["30", "29", "28", "31", "32"], index=0, key="single_agg_pref")
            single_vlan = st.text_input("AGG VLAN (OPTIONAL)", value="")
            single_if_name = st.text_input("AGG INTERFACE NAME", value=aggregation_name or f"Agg_{available_ports[0]}")
            single_mtu = st.text_input("AGG MTU (OPTIONAL)", value="9216")
        else:
            single_port = st.selectbox("PORT", options=available_ports, index=0, key="single_port")
            single_ip = st.text_input("BACKHAUL IP (NO PREFIX)", value="")
            single_prefix = st.selectbox("BACKHAUL PREFIX (CIDR)", ["30", "29", "28", "31", "32"], index=0, key="single_pref")
            single_vlan = st.text_input("BACKHAUL VLAN (E.G. 228)", value="")
            single_if_name = st.text_input("INTERFACE NAME", value=f"Port_{single_port}")
            single_mtu = st.text_input("MTU (OPTIONAL)", value="9216")

    else:
        st.subheader("DUAL BACKHAUL")
        if model != "3903":
            aggregation_enabled = st.checkbox("ENABLE AGGREGATION FOR BACKHAULS", value=False)
        else:
            aggregation_enabled = False

        # Primary
        st.markdown("---")
        st.markdown("**PRIMARY BACKHAUL**")
        if aggregation_enabled:
            primary_agg_name = st.text_input("PRIMARY AGGREGATION NAME", value="PrimaryAgg")
            primary_port = st.multiselect("PRIMARY AGG MEMBER PORTS (select one or more)", options=available_ports, default=available_ports[:1], key="primary_agg_members")
            primary_ip = st.text_input("PRIMARY AGG BACKHAUL IP", value="")
            primary_prefix = st.selectbox("PRIMARY AGG BACKHAUL PREFIX (CIDR)", ["30", "29", "28", "31", "32"], index=0, key="primary_agg_pref")
            primary_vlan = st.text_input("PRIMARY AGG VLAN", value="")
            primary_if_name = st.text_input("PRIMARY AGG INTERFACE NAME", value=primary_agg_name or "PrimaryAgg")
            primary_mtu = st.text_input("PRIMARY AGG MTU (OPTIONAL)", value="9216")
        else:
            primary_port = st.selectbox("PRIMARY PORT", options=available_ports, index=0, key="primary_port")
            primary_ip = st.text_input("PRIMARY BACKHAUL IP (NO PREFIX)", value="")
            primary_prefix = st.selectbox("PRIMARY PREFIX (CIDR)", ["30", "29", "28", "31", "32"], index=0, key="primary_pref")
            primary_vlan = st.text_input("PRIMARY VLAN", value="")
            primary_if_name = st.text_input("PRIMARY INTERFACE NAME", value=f"Port_{primary_port}")
            primary_mtu = st.text_input("PRIMARY MTU (OPTIONAL)", value="9216")

        # Secondary
        st.markdown("---")
        st.markdown("**SECONDARY BACKHAUL**")
        if aggregation_enabled:
            secondary_agg_name = st.text_input("SECONDARY AGGREGATION NAME", value="SecondaryAgg")
            secondary_port = st.multiselect("SECONDARY AGG MEMBER PORTS (select one or more)", options=available_ports, default=available_ports[1:2] if len(available_ports) > 1 else available_ports[:1], key="secondary_agg_members")
            secondary_ip = st.text_input("SECONDARY AGG BACKHAUL IP (NO PREFIX)", value="")
            secondary_prefix = st.selectbox("SECONDARY AGG BACKHAUL PREFIX (CIDR)", ["30", "29", "28", "31", "32"], index=0, key="secondary_agg_pref")
            secondary_vlan = st.text_input("SECONDARY AGG VLAN (OPTIONAL)", value="")
            secondary_if_name = st.text_input("SECONDARY AGG INTERFACE NAME", value=secondary_agg_name or "SecondaryAgg")
            secondary_mtu = st.text_input("SECONDARY AGG MTU (OPTIONAL)", value="9216")
        else:
            secondary_port = st.selectbox("SECONDARY PORT", options=available_ports, index=1 if len(available_ports) > 1 else 0, key="secondary_port")
            secondary_ip = st.text_input("SECONDARY BACKHAUL IP (e.g. 172.20.52.34)", value="")
            secondary_prefix = st.selectbox("SECONDARY PREFIX (CIDR)", ["30", "29", "28", "31", "32"], index=0, key="secondary_pref")
            secondary_vlan = st.text_input("SECONDARY VLAN", value="")
            secondary_if_name = st.text_input("SECONDARY INTERFACE NAME", value=f"Port_{secondary_port}")
            secondary_mtu = st.text_input("SECONDARY MTU (OPTIONAL)", value="9216")

    # loopback / gateway
    model_int = int(model) if model.isdigit() else 0
    loopback_ip = st.text_input("LOOPBACK IP (E.G. 172.20.38.240)", value="") if model_int > 3903 else ""
    gateway = st.text_input("GATEWAY IP", value="") if model == "3903" else ""

st.markdown("---")
st.header("OTHER SETTINGS")
ntp_text = st.text_input("NTP SERVERS (COMMA SEPARATED)", value="10.0.111.1")
syslog_text = st.text_input("SYSLOG COLLECTORS (COMMA SEPARATED)", value="172.20.0.249")

if st.button("RENDER CONFIG(S)"):
    if not hostname:
        st.error("NO HOSTNAME PROVIDED")
        st.stop()

    license_keys = [l.strip() for l in license_keys_text.splitlines() if l.strip()]
    ntp_servers = [s.strip() for s in re.split(r"[,\s]+", ntp_text) if s.strip()]
    syslog_collectors = [s.strip() for s in re.split(r"[,\s]+", syslog_text) if s.strip()]

    inputs = {
        "hostname": hostname,
        "model": model,
        "backhaul": backhaul,
        "tacacs_server_1": tacacs_server_1,
        "tacacs_server_2": tacacs_server_2,
        "tacacs_secret": tacacs_secret,
        "license_keys": license_keys,
        "aggregation_enabled": aggregation_enabled,
        "aggregation_name": locals().get("aggregation_name", ""),
        "single_port": locals().get("single_port"),
        "single_ip": locals().get("single_ip", ""),
        "single_prefix": locals().get("single_prefix", "30"),
        "single_vlan": locals().get("single_vlan", ""),
        "single_if_name": locals().get("single_if_name", ""),
        "single_mtu": locals().get("single_mtu", "9216"),
        "primary_port": locals().get("primary_port"),
        "primary_ip": locals().get("primary_ip", ""),
        "primary_prefix": locals().get("primary_prefix", "30"),
        "primary_vlan": locals().get("primary_vlan", ""),
        "primary_if_name": locals().get("primary_if_name", ""),
        "primary_mtu": locals().get("primary_mtu", "9216"),
        "secondary_port": locals().get("secondary_port"),
        "secondary_ip": locals().get("secondary_ip", ""),
        "secondary_prefix": locals().get("secondary_prefix", "30"),
        "secondary_vlan": locals().get("secondary_vlan", ""),
        "secondary_if_name": locals().get("secondary_if_name", ""),
        "secondary_mtu": locals().get("secondary_mtu", "9216"),
        "primary_agg_name": locals().get("primary_agg_name", ""),
        "secondary_agg_name": locals().get("secondary_agg_name", ""),
        "loopback_ip": loopback_ip,
        "gateway": gateway,
        "ntp_servers": ntp_servers,
        "syslog_collectors": syslog_collectors,
    }

    dev = build_device_from_inputs(inputs)

    available_templates = list_templates()
    base_fname, content, tpl_used = render_device(dev, available_templates=available_templates)

    fname_base = base_fname.rsplit(".", 1)[0]
    if append_ts:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fname = f"{fname_base}_{ts}.txt"
    else:
        fname = f"{fname_base}.txt"

    safe_name = safe_filename(fname)
    generated = {safe_name: content}

    st.success(f"RENDERED {len(generated)} FILE(S)")
    st.header("TEMPLATE SELECTION LOG")
    st.write(f"- {hostname} → `{tpl_used}`")

    st.header("PREVIEWS & DOWNLOAD")
    for name, content in generated.items():
        with st.expander(f"PREVIEW: {name}", expanded=False):
            st.code(content, language="text")
            st.download_button("DOWNLOAD TXT", data=content, file_name=name, mime="text/plain")

    zip_bytes = create_zip_from_dict(generated)
    st.download_button("DOWNLOAD ALL AS ZIP", data=zip_bytes, file_name="ciena_configs.zip", mime="application/zip")

st.caption("SECURITY: TACACS SECRETS SHOWN ARE PLACEHOLDERS/REFS. DO NOT USE PLAIN SECRETS IN SOURCE CONTROL.")