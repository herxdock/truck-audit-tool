from datetime import datetime
import io
import json
import os
import zipfile
import pandas as pd
import streamlit as st
from supabase import Client, create_client

# Pagina instellingen
st.set_page_config(
    page_title="Truck Audit Systeem", page_icon="🚛", layout="wide"
)

# ==========================================
# HEFTRUCK & TABLET STYLING (CSS)
# ==========================================
st.markdown(
    """
<style>
    /* ==========================================
       1. ECHT DIKKE RAND ROND ELK CONTROLEBLOK
       ========================================== */
    div[data-testid="stVerticalBlockBorderWrapper"],
    div.stVerticalBlockBorderWrapper {
        border: 6px solid #1e293b !important;
        border-radius: 24px !important;
        background-color: #ffffff !important;
        padding: 24px 20px !important;
        margin-top: 15px !important;
        margin-bottom: 45px !important;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.22) !important;
    }

    .vraag-titel {
        font-size: 28px !important;
        font-weight: 900 !important;
        color: #ffffff !important;
        background-color: #1e293b !important;
        padding: 14px 18px !important;
        border-radius: 14px !important;
        margin-bottom: 20px !important;
        line-line: 1.3 !important;
    }

    /* 2. GROTE TOUCHKNOPPEN */
    div.stButton > button, 
    div[data-testid="stButton"] > button {
        min-height: 90px !important;
        border-radius: 18px !important;
        margin-bottom: 10px !important;
        box-shadow: 0 5px 10px rgba(0,0,0,0.18) !important;
        border: 2px solid #bbb !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 10px 15px !important;
    }

    div.stButton > button p,
    div[data-testid="stButton"] > button p,
    div.stButton > button div[data-testid="stMarkdownContainer"] p {
        font-size: 32px !important;
        font-weight: 900 !important;
        line-height: 1.2 !important;
        margin: 0 !important;
        text-align: center !important;
    }

    div.stButton > button[kind="primary"] {
        background-color: #0d6efd !important;
        border: 4px solid #084298 !important;
    }
    div.stButton > button[kind="primary"] p {
        color: #ffffff !important;
    }

    div.stButton > button[kind="secondary"] {
        background-color: #f1f3f5 !important;
    }
    div.stButton > button[kind="secondary"] p {
        color: #212529 !important;
    }

    /* 3. OK & NOK KNOPPEN */
    div[class*="st-key-btn_ok_"] button[kind="primary"] {
        background-color: #198754 !important;
        border: 4px solid #0f5132 !important;
    }
    div[class*="st-key-btn_ok_"] button[kind="primary"] p {
        color: #ffffff !important;
    }

    div[class*="st-key-btn_nok_"] button[kind="primary"] {
        background-color: #dc3545 !important;
        border: 4px solid #842029 !important;
    }
    div[class*="st-key-btn_nok_"] button[kind="primary"] p {
        color: #ffffff !important;
    }

    /* 4. INVOER & CAMERA */
    div[data-testid="stTextInput"] input {
        font-size: 22px !important;
        min-height: 60px !important;
        border-radius: 12px !important;
        border: 2px solid #ccc !important;
    }

    div[class*="st-key-open_cam_"] button,
    div[class*="st-key-close_cam_"] button {
        min-height: 65px !important;
        border-radius: 14px !important;
        background-color: #e9ecef !important;
    }
    div[class*="st-key-open_cam_"] button p,
    div[class*="st-key-close_cam_"] button p {
        font-size: 22px !important;
        color: #333 !important;
    }

    div[data-testid="stCameraInput"] button {
        min-height: 75px !important;
    }
    div[data-testid="stCameraInput"] button p {
        font-size: 24px !important;
        font-weight: 800 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# SUPABASE CLIENT SETUP
# ==========================================
@st.cache_resource
def get_supabase() -> Client:
  if "supabase" in st.secrets:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)
  return None


def get_setting(key, default):
  client = get_supabase()
  if client:
    try:
      res = (
          client.table("settings")
          .select("value")
          .eq("key", key)
          .limit(1)
          .execute()
      )
      if res.data and len(res.data) > 0:
        return res.data[0]["value"]
    except Exception:
      pass
  return default


def set_setting(key, value):
  client = get_supabase()
  if client:
    try:
      client.table("settings").upsert({"key": key, "value": value}).execute()
    except Exception as e:
      st.error(f"Fout bij opslaan van instelling: {e}")


# Standaard instellingen
standaard_vragen = {
    "Load": [
        "1. Laadkwaliteit & gewichtsverdeling",
        "2. Zekering / Spanbanden / Balken geplaatst",
        "3. Geen zichtbare laadschade aan goederen",
        "4. Sluiten & vergrendelen van de trailer",
        "5. Vrachtdocumenten getekend en meegegeven",
    ],
    "Unload": [
        "1. Visuele controle bij openen trailer (verschuivingen?)",
        "2. Schade aan binnenkomende goederen",
        "3. Trailer vloer en wanden geïnspecteerd op schade",
        "4. Netheid van de lege laadruimte (veegschoon)",
        "5. Vrachtbrief / CMR afgetekend met eventuele voorbehouden",
    ],
}

standaard_trucks = [
    "Truck 01",
    "Truck 02",
    "Truck 03",
    "Truck 04",
    "Truck 05",
    "Truck 06",
]
standaard_klanten = ["BMW", "Toyota", "Scania", "Grieshaber", "TS-Lux"]

standaard_klant_trucks = {
    "BMW": ["Truck 01", "Truck 02"],
    "Toyota": ["Truck 02", "Truck 03"],
    "Scania": ["Truck 03", "Truck 04"],
    "Grieshaber": ["Truck 04", "Truck 05"],
    "TS-Lux": ["Truck 01", "Truck 05", "Truck 06"],
}

vragen_per_actie = get_setting("vragen_per_actie", standaard_vragen)
trucks_lijst = get_setting("trucks", standaard_trucks)
klanten_lijst = get_setting("klanten", standaard_klanten)
klant_trucks_map = get_setting("klant_trucks", standaard_klant_trucks)

# ==========================================
# INLOGGEN VIA STREAMLIT SECRETS
# ==========================================
def verify_login(username, password):
  user_clean = username.strip().lower()
  pass_clean = password.strip()

  if "admins" in st.secrets:
    for admin_user, admin_pass in st.secrets["admins"].items():
      if (
          str(admin_user).lower() == user_clean
          and str(admin_pass) == pass_clean
      ):
        return {"username": str(admin_user), "role": "admin"}

  groep = st.secrets.get("auditors", st.secrets.get("inspecteurs", None))
  if groep:
    for audit_user, audit_pass in groep.items():
      if (
          str(audit_user).lower() == user_clean
          and str(audit_pass) == pass_clean
      ):
        return {"username": str(audit_user), "role": "user"}

  return None


if "logged_in" not in st.session_state:
  st.session_state.logged_in = False
  st.session_state.user = None

if not st.session_state.logged_in:
  col_l, col_center, col_r = st.columns([1, 2, 1])
  with col_center:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.title("🔐 Login Truck Audit")
    with st.form("login_form"):
      user_input = st.text_input("Gebruikersnaam")
      pass_input = st.text_input("Wachtwoord", type="password")
      submit = st.form_submit_button("Inloggen", use_container_width=True)

      if submit:
        user_info = verify_login(user_input, pass_input)
        if user_info:
          st.session_state.logged_in = True
          st.session_state.user = user_info
          st.rerun()
        else:
          st.error("Onjuiste gebruikersnaam of wachtwoord.")
  st.stop()

# ==========================================
# HOOFDMENU & RECHTEN
# ==========================================
huidige_gebruiker = st.session_state.user["username"]
is_admin = st.session_state.user["role"] == "admin"

st.sidebar.markdown(f"### 👤 Ingelogd: `{huidige_gebruiker}`")
st.sidebar.caption(f"Rol: {'Beheerder' if is_admin else 'Auditor'}")

if st.sidebar.button("🚪 Uitloggen", use_container_width=True):
  st.session_state.logged_in = False
  st.session_state.user = None
  st.rerun()

st.sidebar.write("---")

if is_admin:
  menu = st.sidebar.radio(
      "Navigatie",
      [
          "📋 Nieuwe Audit",
          "📊 Historie & Foto's",
          "⚙️ Beheer & Instellingen",
      ],
  )
else:
  st.sidebar.info("📋 Modus: Audit Uitvoeren")
  menu = "📋 Nieuwe Audit"

# ==========================================
# ONDERDEEL 1: NIEUWE AUDIT (GROTE KNOPPEN)
# ==========================================
if menu == "📋 Nieuwe Audit":
  st.title("📋 Nieuwe Truck Audit")

  if "sel_actie" not in st.session_state:
    st.session_state.sel_actie = None
  if "sel_klant" not in st.session_state:
    st.session_state.sel_klant = None
  if "sel_truck" not in st.session_state:
    st.session_state.sel_truck = None

  col_head1, col_head2 = st.columns([3, 1])
  with col_head1:
    st.caption(
        f"Inspecteur: **{huidige_gebruiker}** |"
        f" {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    )
  with col_head2:
    if st.session_state.sel_actie is not None:
      if st.button("🔄 Reset Selectie", use_container_width=True):
        st.session_state.sel_actie = None
        st.session_state.sel_klant = None
        st.session_state.sel_truck = None
        st.rerun()

  # STAP 1: GROTE ACTIE KNOPPEN
  st.subheader("1. Kies Actie")
  c1, c2 = st.columns(2)
  with c1:
    is_load = st.session_state.sel_actie == "Load"
    if st.button(
        "📦 LOAD (Laden)",
        use_container_width=True,
        type="primary" if is_load else "secondary",
    ):
      st.session_state.sel_actie = "Load"
      st.rerun()
  with c2:
    is_unload = st.session_state.sel_actie == "Unload"
    if st.button(
        "🚚 UNLOAD (Lossen)",
        use_container_width=True,
        type="primary" if is_unload else "secondary",
    ):
      st.session_state.sel_actie = "Unload"
      st.rerun()

  # STAP 2: GROTE KLANT KNOPPEN
  if st.session_state.sel_actie:
    st.write("---")
    st.subheader(f"2. Kies Klant ({st.session_state.sel_actie})")

    kolommen_per_rij = 2
    for i in range(0, len(klanten_lijst), kolommen_per_rij):
      cols = st.columns(kolommen_per_rij)
      for j, klant_naam in enumerate(klanten_lijst[i : i + kolommen_per_rij]):
        with cols[j]:
          is_active = st.session_state.sel_klant == klant_naam
          if st.button(
              f"🏢 {klant_naam}",
              key=f"btn_k_{klant_naam}",
              use_container_width=True,
              type="primary" if is_active else "secondary",
          ):
            st.session_state.sel_klant = klant_naam
            st.session_state.sel_truck = None
            st.rerun()

  # STAP 3: GEFILTERDE TRUCK KNOPPEN
  if st.session_state.sel_klant:
    st.write("---")
    st.subheader(f"3. Kies Truck ({st.session_state.sel_klant})")

    gekoppelde_trucks = klant_trucks_map.get(
        st.session_state.sel_klant, trucks_lijst
    )

    if not gekoppelde_trucks:
      st.warning(
          f"⚠️ Geen trucks gekoppeld aan '{st.session_state.sel_klant}' in het"
          " beheerpaneel."
      )
    else:
      kolommen_trucks = 2
      for i in range(0, len(gekoppelde_trucks), kolommen_trucks):
        cols = st.columns(kolommen_trucks)
        for j, truck_naam in enumerate(
            gekoppelde_trucks[i : i + kolommen_trucks]
        ):
          with cols[j]:
            is_active_truck = st.session_state.sel_truck == truck_naam
            if st.button(
                f"🚛 {truck_naam}",
                key=f"btn_t_{truck_naam}",
                use_container_width=True,
                type="primary" if is_active_truck else "secondary",
            ):
              st.session_state.sel_truck = truck_naam
              st.rerun()

  # STAP 4: CONTROLEPUNTEN MET 6PX DIKKE KADERS
  if (
      st.session_state.sel_actie
      and st.session_state.sel_klant
      and st.session_state.sel_truck
  ):
    st.write("---")
    st.info(
        f"Gekozen: **{st.session_state.sel_actie}** |"
        f" **{st.session_state.sel_klant}** | **{st.session_state.sel_truck}**"
    )
    st.subheader(f"4. Controlepunten voor {st.session_state.sel_actie}")

    actieve_vragen = vragen_per_actie.get(st.session_state.sel_actie, [])

    if not actieve_vragen:
      st.warning(
          f"Geen controlepunten geconfigureerd voor '{st.session_state.sel_actie}'."
      )

    antwoorden = []
    for i, vraag in enumerate(actieve_vragen):
      with st.container(border=True):
        st.markdown(
            f"<div class='vraag-titel'>{vraag}</div>", unsafe_allow_html=True
        )

        huidige_status = st.session_state.get(f"status_{i}", "OK")

        c_ok, c_nok = st.columns(2)
        with c_ok:
          is_ok = huidige_status == "OK"
          if st.button(
              "🟢 OK",
              key=f"btn_ok_{i}",
              use_container_width=True,
              type="primary" if is_ok else "secondary",
          ):
            st.session_state[f"status_{i}"] = "OK"
            st.rerun()
        with c_nok:
          is_nok = huidige_status == "NOK"
          if st.button(
              "🔴 NOK",
              key=f"btn_nok_{i}",
              use_container_width=True,
              type="primary" if is_nok else "secondary",
          ):
            st.session_state[f"status_{i}"] = "NOK"
            st.rerun()

        comment = st.text_input(
            "Opmerking (optioneel):",
            key=f"comm_{i}",
            placeholder="Typ hier eventuele opmerkingen of schades...",
        )

        foto_bestandsnaam = st.session_state.get(f"saved_foto_{i}", "")
        camera_open = st.session_state.get(f"show_cam_{i}", False)

        if not camera_open:
          label_cam = (
              "📸 Foto opnieuw nemen"
              if foto_bestandsnaam
              else "📷 Take picture (Foto toevoegen)"
          )
          if st.button(
              label_cam, key=f"open_cam_{i}", use_container_width=True
          ):
            st.session_state[f"show_cam_{i}"] = True
            st.rerun()
        else:
          foto = st.camera_input(f"📷 Richt camera voor punt {i+1}", key=f"foto_{i}")
          if foto is not None:
            tijd_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_truck = (
                "".join(
                    c
                    for c in str(st.session_state.sel_truck)
                    if c.isalnum() or c in (" ", "_", "-")
                )
                .strip()
                .replace(" ", "_")
            )
            foto_bestandsnaam = f"{safe_truck}_v{i+1}_{tijd_tag}.png"
            foto_bytes = foto.getvalue()

            st.session_state[f"saved_foto_{i}"] = foto_bestandsnaam
            st.session_state[f"saved_bytes_{i}"] = foto_bytes
            st.success("✅ Foto succesvol vastgelegd!")

          if st.button(
              "✖️ Camera sluiten",
              key=f"close_cam_{i}",
              use_container_width=True,
          ):
            st.session_state[f"show_cam_{i}"] = False
            st.rerun()

        if foto_bestandsnaam:
          st.caption(f"📁 Opgeslagen fotobestand: `{foto_bestandsnaam}`")

        antwoorden.append({
            "vraag": vraag,
            "status": huidige_status,
            "commentaar": comment,
            "foto_pad": foto_bestandsnaam,
            "foto_bytes": st.session_state.get(f"saved_bytes_{i}", None),
        })

    # OPSLAAN KNOP
    st.write("<br>", unsafe_allow_html=True)
    if st.button(
        "💾 AUDIT VOLTOOIEN EN OPSLAAN",
        type="primary",
        use_container_width=True,
    ):
      now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      audit_id = int(datetime.now().strftime("%y%m%d%H%M%S"))
      client = get_supabase()

      if not client:
        st.error(
            "Supabase verbinding niet gevonden. Controleer je secrets instelling."
        )
      else:
        # 1. Upload alle gemaakte foto's naar de Supabase Bucket
        foto_urls = {}
        for item in antwoorden:
          fn = item.get("foto_pad")
          fb = item.get("foto_bytes")
          if fn and fb:
            try:
              client.storage.from_("audit-fotos").upload(
                  path=fn,
                  file=fb,
                  file_options={"content-type": "image/png", "upsert": "true"},
              )
              url = client.storage.from_("audit-fotos").get_public_url(fn)
              foto_urls[fn] = url
            except Exception as e:
              st.warning(f"Foto upload waarschuwing: {e}")

        # 2. Sla de audit hoofdregel op in de tabel 'audits'
        try:
          client.table("audits").insert({
              "id": audit_id,
              "timestamp": now_str,
              "actie": st.session_state.sel_actie,
              "klant": st.session_state.sel_klant,
              "truck": st.session_state.sel_truck,
              "auditor": huidige_gebruiker,
          }).execute()

          # 3. Sla alle controlepunten op in de tabel 'audit_items'
          items_to_insert = []
          for item in antwoorden:
            fn = item["foto_pad"]
            items_to_insert.append({
                "audit_id": audit_id,
                "vraag": item["vraag"],
                "status": item["status"],
                "commentaar": item["commentaar"],
                "foto_url": foto_urls.get(fn, ""),
            })

          client.table("audit_items").insert(items_to_insert).execute()
          st.success(f"✅ Audit #{audit_id} succesvol permanent opgeslagen!")
        except Exception as e:
          st.error(f"Fout bij opslaan in database: {e}")

      # Reset selecties
      st.session_state.sel_actie = None
      st.session_state.sel_klant = None
      st.session_state.sel_truck = None
      for i in range(len(actieve_vragen)):
        st.session_state.pop(f"status_{i}", None)
        st.session_state.pop(f"comm_{i}", None)
        st.session_state.pop(f"show_cam_{i}", None)
        st.session_state.pop(f"saved_foto_{i}", None)
        st.session_state.pop(f"saved_bytes_{i}", None)
        st.session_state.pop(f"foto_{i}", None)
      st.rerun()

# ==========================================
# ONDERDEEL 2: HISTORIE, KPI'S & RAPPORTAGE
# ==========================================
elif menu == "📊 Historie & Foto's" and is_admin:
  st.title("📊 Kwaliteitscontrole & Rapportage")

  client = get_supabase()
  ritten_lijst = []
  items_lijst = []

  if client:
    try:
      res_audits = (
          client.table("audits")
          .select("*, audit_items(*)")
          .order("id", desc=True)
          .execute()
      )
      if res_audits.data:
        for audit in res_audits.data:
          ritten_lijst.append({
              "audit_id": audit["id"],
              "timestamp": audit["timestamp"],
              "actie": audit["actie"],
              "klant": audit["klant"],
              "truck": audit["truck"],
              "auditor": audit["auditor"],
          })
          for it in audit.get("audit_items", []):
            items_lijst.append({
                "audit_id": audit["id"],
                "timestamp": audit["timestamp"],
                "actie": audit["actie"],
                "klant": audit["klant"],
                "truck": audit["truck"],
                "auditor": audit["auditor"],
                "vraag": it["vraag"],
                "status": it["status"],
                "commentaar": it["commentaar"],
                "foto_url": it.get("foto_url", ""),
            })
    except Exception as e:
      st.error(f"Fout bij ophalen historie: {e}")

  if not ritten_lijst:
    st.info(
        "Er zijn nog geen audits geregistreerd in de cloud. Voer eerst een"
        " audit uit!"
    )
  else:
    ritten_df = pd.DataFrame(ritten_lijst)
    compleet_df = pd.DataFrame(items_lijst)

    # Converteer timestamp naar datumformaat voor betrouwbare datumselectie
    try:
      ritten_df["datum"] = pd.to_datetime(ritten_df["timestamp"]).dt.date
    except Exception:
      ritten_df["datum"] = datetime.now().date()

    # --- 1. FILTERPANEEL ---
    st.subheader("🔍 Filters & Periode Selectie")

    col_datum1, col_datum2 = st.columns(2)
    min_db_datum = ritten_df["datum"].min()
    max_db_datum = ritten_df["datum"].max()

    with col_datum1:
      van_datum = st.date_input("📅 Van datum:", value=min_db_datum)
    with col_datum2:
      tot_datum = st.date_input("📅 Tot en met datum:", value=max_db_datum)

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
      filter_actie = st.multiselect(
          "Filter op Actie:",
          options=sorted(ritten_df["actie"].unique().tolist()),
          default=ritten_df["actie"].unique().tolist(),
      )
    with col_f2:
      filter_klant = st.multiselect(
          "Filter op Klant:",
          options=sorted(ritten_df["klant"].unique().tolist()),
          default=ritten_df["klant"].unique().tolist(),
      )
    with col_f3:
      filter_truck = st.multiselect(
          "Filter op Truck:",
          options=sorted(ritten_df["truck"].unique().tolist()),
          default=ritten_df["truck"].unique().tolist(),
      )

    alleen_nok = st.checkbox(
        "⚠️ Toon alleen audits met afwijking / schade (minstens één NOK)",
        value=False,
    )

    # Toepassen van de filters
    mask = (
        (ritten_df["datum"] >= van_datum)
        & (ritten_df["datum"] <= tot_datum)
        & (ritten_df["actie"].isin(filter_actie))
        & (ritten_df["klant"].isin(filter_klant))
        & (ritten_df["truck"].isin(filter_truck))
    )
    gefilterde_ritten = ritten_df[mask]

    # Indien 'alleen NOK' aangevinkt staat
    if alleen_nok:
      nok_audit_ids = compleet_df[compleet_df["status"] == "NOK"][
          "audit_id"
      ].unique()
      gefilterde_ritten = gefilterde_ritten[
          gefilterde_ritten["audit_id"].isin(nok_audit_ids)
      ]

    # --- 2. KPI METRICS (SCOREBORD) ---
    st.write("---")
    totaal_aantal = len(gefilterde_ritten)

    if totaal_aantal == 0:
      st.warning(
          "Geen audits gevonden voor deze specifieke filter-combinatie."
      )
    else:
      # Items die horen bij de gefilterde ritten
      gefilterde_items = compleet_df[
          compleet_df["audit_id"].isin(gefilterde_ritten["audit_id"])
      ]

      # Bereken statistieken
      ritten_met_nok_aantal = gefilterde_items[
          gefilterde_items["status"] == "NOK"
      ]["audit_id"].nunique()
      ritten_100_ok_aantal = totaal_aantal - ritten_met_nok_aantal
      pct_ok = round((ritten_100_ok_aantal / totaal_aantal) * 100, 1)
      totaal_fotos = gefilterde_items[gefilterde_items["foto_url"] != ""][
          "foto_url"
      ].nunique()

      # Toon 4 KPI kaarten
      kpi1, kpi2, kpi3, kpi4 = st.columns(4)
      kpi1.metric("📋 Totaal Audits", f"{totaal_aantal}")
      kpi2.metric("🟢 100% Goedgekeurd", f"{ritten_100_ok_aantal}", f"{pct_ok}%")
      kpi3.metric(
          "🔴 Met Afwijking (NOK)",
          f"{ritten_met_nok_aantal}",
          f"-{round(100 - pct_ok, 1)}%" if ritten_met_nok_aantal > 0 else "0%",
      )
      kpi4.metric("📷 Gemaakte Foto's", f"{totaal_fotos}")

      # --- 3. RAPPORT DOWNLOADS (EXECUTIVE & DETAIL) ---
      st.write("---")
      st.subheader("📥 Export & Rapportages")
      down_col1, down_col2 = st.columns(2)

      # A. Management Samenvatting (1 rij per audit)
      samenvatting_rijen = []
      for _, rit_info in gefilterde_ritten.iterrows():
        a_id = rit_info["audit_id"]
        sub_items = gefilterde_items[gefilterde_items["audit_id"] == a_id]
        aantal_ok = len(sub_items[sub_items["status"] == "OK"])
        aantal_nok = len(sub_items[sub_items["status"] == "NOK"])
        heeft_nok = aantal_nok > 0

        # Alle opmerkingen samenvoegen tot 1 nette leesbare tekst
        opmerkingen_tekst = " | ".join([
            f"{r['vraag']}: {r['commentaar']}"
            for _, r in sub_items.iterrows()
            if pd.notna(r["commentaar"]) and str(r["commentaar"]).strip() != ""
        ])

        samenvatting_rijen.append({
            "Audit ID": a_id,
            "Tijdstip": rit_info["timestamp"],
            "Actie": rit_info["actie"],
            "Klant": rit_info["klant"],
            "Truck": rit_info["truck"],
            "Inspecteur": rit_info["auditor"],
            "Eindoordeel": "⚠️ AFWIJKING" if heeft_nok else "✅ 100% OK",
            "Aantal OK": aantal_ok,
            "Aantal NOK": aantal_nok,
            "Opmerkingen": opmerkingen_tekst,
        })

      df_management_rapport = pd.DataFrame(samenvatting_rijen)
      csv_management = df_management_rapport.to_csv(index=False).encode("utf-8")

      with down_col1:
        st.download_button(
            label="📄 Download Samenvatting (1 regel per rit)",
            data=csv_management,
            file_name=f"audit_samenvatting_{van_datum}_tot_{tot_datum}.csv",
            mime="text/csv",
            use_container_width=True,
        )

      # B. Volledig Detailrapport (inclusief directe fotolinks)
      csv_detail = gefilterde_items.to_csv(index=False).encode("utf-8")
      with down_col2:
        st.download_button(
            label="📋 Download Detailrapport (Alle controlepunten & fotolinks)",
            data=csv_detail,
            file_name=f"audit_details_{van_datum}_tot_{tot_datum}.csv",
            mime="text/csv",
            use_container_width=True,
        )

      # --- 4. VISUEEL RITTENOVERZICHT ---
      st.write("---")
      st.subheader(
          f"Rittenoverzicht ({totaal_aantal} audits in geselecteerde periode)"
      )

      for _, rit in gefilterde_ritten.iterrows():
        items = gefilterde_items[
            gefilterde_items["audit_id"] == rit["audit_id"]
        ]
        rit_heeft_nok = "NOK" in items["status"].values

        # Kleur en statusbadge in de titel van de rit
        status_icoon = "🔴" if rit_heeft_nok else "🟢"
        oordeel_label = "⚠️ AFWIJKING" if rit_heeft_nok else "100% OK"
        titel = f"{status_icoon} Audit #{rit['audit_id']} [{oordeel_label}] | {rit['truck']} ({rit['klant']}) - {rit['actie']} om {rit['timestamp']}"

        with st.expander(titel):
          st.write(f"**Inspecteur:** {rit['auditor']}")

          for _, it in items.iterrows():
            kleur = "🟢" if it["status"] == "OK" else "🔴"
            st.markdown(
                f"**{kleur} {it['vraag']}** — Status: **{it['status']}**"
            )
            if pd.notna(it["commentaar"]) and it["commentaar"]:
              st.write(f"💬 Opmerking: *{it['commentaar']}*")

            if pd.notna(it["foto_url"]) and it["foto_url"]:
              st.image(
                  it["foto_url"],
                  caption=f"Foto inspectiepunt",
                  width=350,
              )
            st.write("---")

# ==========================================
# ONDERDEEL 3: BEHEER & INSTELLINGEN (ADMIN)
# ==========================================
elif menu == "⚙️ Beheer & Instellingen" and is_admin:
  st.title("⚙️ Beheerpaneel")
  st.caption("Beheer trucks, klanten, koppelingen en controlepunten.")

  tab1, tab2, tab3, tab4 = st.tabs([
      "🔗 Klanten & Trucks Koppelen",
      "🏢 Klanten",
      "🚛 Trucks",
      "❓ Vragen per Actie",
  ])

  with tab1:
    st.subheader("Koppel vrachtwagens aan een klant")
    gekozen_klant = st.selectbox("Kies Klant", klanten_lijst)
    huidige_gekoppelde = klant_trucks_map.get(gekozen_klant, [])

    geselecteerde_trucks = st.multiselect(
        f"Beschikbare trucks voor '{gekozen_klant}':",
        options=trucks_lijst,
        default=[t for t in huidige_gekoppelde if t in trucks_lijst],
    )

    if st.button("💾 Koppeling Opslaan", type="primary"):
      klant_trucks_map[gekozen_klant] = geselecteerde_trucks
      set_setting("klant_trucks", klant_trucks_map)
      st.success(
          f"Opgeslagen! {len(geselecteerde_trucks)} trucks gekoppeld aan"
          f" {gekozen_klant}."
      )
      st.rerun()

  with tab2:
    nieuwe_klant = st.text_input("Nieuwe klant toevoegen")
    if st.button("Voeg klant toe"):
      if nieuwe_klant and nieuwe_klant not in klanten_lijst:
        klanten_lijst.append(nieuwe_klant)
        set_setting("klanten", klanten_lijst)
        st.rerun()

    del_klant = st.selectbox("Verwijder een klant", ["---"] + klanten_lijst)
    if st.button("Verwijder klant"):
      if del_klant != "---":
        klanten_lijst.remove(del_klant)
        set_setting("klanten", klanten_lijst)
        if del_klant in klant_trucks_map:
          del klant_trucks_map[del_klant]
          set_setting("klant_trucks", klant_trucks_map)
        st.rerun()
    st.write("Actieve klanten:", klanten_lijst)

  with tab3:
    nieuwe_truck = st.text_input("Nieuwe vrachtwagen toevoegen")
    if st.button("Voeg truck toe"):
      if nieuwe_truck and nieuwe_truck not in trucks_lijst:
        trucks_lijst.append(nieuwe_truck)
        set_setting("trucks", trucks_lijst)
        st.rerun()

    del_truck = st.selectbox("Verwijder een truck", ["---"] + trucks_lijst)
    if st.button("Verwijder truck"):
      if del_truck != "---":
        trucks_lijst.remove(del_truck)
        set_setting("trucks", trucks_lijst)
        st.rerun()
    st.write("Actieve trucks:", trucks_lijst)

  with tab4:
    st.subheader("Controlepunten beheren per Actie")
    actie_keuze = st.radio(
        "Kies welke vragenset je wilt aanpassen:",
        ["Load", "Unload"],
        horizontal=True,
    )

    vragen_deze_actie = vragen_per_actie.get(actie_keuze, [])

    nieuwe_vraag = st.text_input(f"Nieuw controlepunt toevoegen voor {actie_keuze}")
    if st.button(f"Voeg vraag toe aan {actie_keuze}"):
      if nieuwe_vraag and nieuwe_vraag not in vragen_deze_actie:
        vragen_deze_actie.append(nieuwe_vraag)
        vragen_per_actie[actie_keuze] = vragen_deze_actie
        set_setting("vragen_per_actie", vragen_per_actie)
        st.rerun()

    del_vraag = st.selectbox(
        f"Verwijder een vraag uit {actie_keuze}", ["---"] + vragen_deze_actie
    )
    if st.button(f"Verwijder vraag uit {actie_keuze}"):
      if del_vraag != "---":
        vragen_deze_actie.remove(del_vraag)
        vragen_per_actie[actie_keuze] = vragen_deze_actie
        set_setting("vragen_per_actie", vragen_per_actie)
        st.rerun()

    st.write(f"**Actieve controlepunten voor {actie_keuze}:**")
    for idx, v in enumerate(vragen_deze_actie):
      st.write(f"- {v}")
