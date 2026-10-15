from datetime import datetime
import io
import json
import os
import urllib.request
import zipfile
from zoneinfo import ZoneInfo
from fpdf import FPDF
import pandas as pd
import streamlit as st
from supabase import Client, create_client

# ==========================================
# BRUSSELSE TIJDZONE HELPER
# ==========================================
BRUSSEL_TZ = ZoneInfo("Europe/Brussels")


def get_now():
  return datetime.now(BRUSSEL_TZ)


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
        line-height: 1.3 !important;
    }

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
# INLOGGEN VIA STREAMLIT SECRETS (DIRECT VOORAAN)
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

# ALS NIET INGELOGD: TOON DIRECT HET INLOGSCHERM ZONDER NETWERKVERTRAGING
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
# SUPABASE CLIENT SETUP (PAS NA LOGIN)
# ==========================================
@st.cache_resource
def get_supabase() -> Client:
  if "supabase" in st.secrets:
    try:
      url = st.secrets["supabase"]["url"]
      key = st.secrets["supabase"]["key"]
      return create_client(url, key)
    except Exception:
      return None
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

# Deze worden nu pas opgehaald NA een geldige login
vragen_per_actie = get_setting("vragen_per_actie", standaard_vragen)
trucks_lijst = get_setting("trucks", standaard_trucks)
klanten_lijst = get_setting("klanten", standaard_klanten)
klant_trucks_map = get_setting("klant_trucks", standaard_klant_trucks)

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
# PDF RAPPORTAGE GENERATOR (FPDF2)
# ==========================================
class AuditPDF(FPDF):

  def __init__(self, titel_rapport="TRUCK AUDIT RAPPORT"):
    super().__init__()
    self.titel_rapport = titel_rapport

  def header(self):
    heeft_logo = False
    if os.path.exists("logo.png"):
      try:
        self.image("logo.png", 10, 8, 30)
        heeft_logo = True
      except Exception:
        heeft_logo = False

    x_tekst = 44 if heeft_logo else 10
    self.set_xy(x_tekst, 11)

    self.set_font("helvetica", "B", 12)
    self.set_text_color(30, 41, 59)
    self.cell(95, 7, self.titel_rapport, border=False, align="L")

    self.set_font("helvetica", "", 9)
    self.set_text_color(100, 116, 139)
    self.cell(
        0,
        7,
        f"Gegenereerd: {get_now().strftime('%d-%m-%Y %H:%M')}",
        border=False,
        align="R",
    )

    self.set_xy(10, 24)
    self.set_draw_color(203, 213, 225)
    self.line(10, 24, 200, 24)
    self.ln(4)

  def footer(self):
    self.set_y(-15)
    self.set_font("helvetica", "I", 8)
    self.set_text_color(148, 163, 184)
    self.cell(
        0,
        10,
        f"Pagina {self.page_no()}/{{nb}} - Vertrouwelijk Kwaliteitsrapport",
        align="C",
    )


def download_afbeelding_bytes(url):
  try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
      return resp.read()
  except Exception:
    return None


def genereer_pdf_rapport(
    gefilterde_ritten,
    gefilterde_items,
    van_datum,
    tot_datum,
    is_enkele_rit=False,
):
  titel = (
      "TRUCK AUDIT DOSSIER"
      if is_enkele_rit
      else "PERIODIEK AUDIT- & KWALITEITSRAPPORT"
  )
  pdf = AuditPDF(titel_rapport=titel)
  pdf.alias_nb_pages()
  pdf.set_auto_page_break(auto=True, margin=15)
  pdf.add_page()

  if not is_enkele_rit:
    pdf.set_font("helvetica", "B", 12)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 8, "  1. MANAGEMENT SAMENVATTING", fill=True, ln=True)
    pdf.ln(2)

    pdf.set_font("helvetica", "", 9)
    pdf.cell(40, 6, "Geselecteerde Periode:", border=False)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(
        0,
        6,
        f"{van_datum.strftime('%d-%m-%Y')} t/m {tot_datum.strftime('%d-%m-%Y')}",
        ln=True,
    )

    totaal = len(gefilterde_ritten)
    ritten_met_nok = gefilterde_items[gefilterde_items["status"] == "NOK"][
        "audit_id"
    ].nunique()
    ritten_ok = totaal - ritten_met_nok
    pct_ok = round((ritten_ok / totaal) * 100, 1) if totaal > 0 else 0

    pdf.set_font("helvetica", "", 9)
    pdf.cell(40, 6, "Totaal Aantal Audits:", border=False)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(0, 6, f"{totaal}", ln=True)

    pdf.set_font("helvetica", "", 9)
    pdf.cell(40, 6, "Kwaliteitsscore (OK):", border=False)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(25, 135, 84)
    pdf.cell(0, 6, f"{ritten_ok} ritten 100% goedgekeurd ({pct_ok}%)", ln=True)

    if ritten_met_nok > 0:
      pdf.set_font("helvetica", "", 9)
      pdf.set_text_color(15, 23, 42)
      pdf.cell(40, 6, "Afwijkingen / Schades:", border=False)
      pdf.set_font("helvetica", "B", 9)
      pdf.set_text_color(220, 53, 69)
      pdf.cell(
          0,
          6,
          f"{ritten_met_nok} ritten met minstens 1 afwijking (NOK)",
          ln=True,
      )

    pdf.ln(5)

    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(20, 7, "Rit #", fill=True, align="C")
    pdf.cell(32, 7, "Datum & Tijd", fill=True)
    pdf.cell(20, 7, "Actie", fill=True)
    pdf.cell(28, 7, "Klant", fill=True)
    pdf.cell(28, 7, "Truck", fill=True)
    pdf.cell(32, 7, "Inspecteur", fill=True)
    pdf.cell(30, 7, "Oordeel", fill=True, align="C")
    pdf.ln(7)

    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(15, 23, 42)

    for idx, rit in gefilterde_ritten.iterrows():
      sub = gefilterde_items[gefilterde_items["audit_id"] == rit["audit_id"]]
      heeft_nok = "NOK" in sub["status"].values
      bg_color = (254, 242, 242) if heeft_nok else (255, 255, 255)

      pdf.set_fill_color(*bg_color)
      pdf.cell(20, 6, f"#{rit['audit_id']}", border="B", fill=True, align="C")
      pdf.cell(32, 6, str(rit["timestamp"])[:16], border="B", fill=True)
      pdf.cell(20, 6, str(rit["actie"]), border="B", fill=True)
      pdf.cell(28, 6, str(rit["klant"]), border="B", fill=True)
      pdf.cell(28, 6, str(rit["truck"]), border="B", fill=True)
      pdf.cell(32, 6, str(rit["auditor"])[:18], border="B", fill=True)

      if heeft_nok:
        pdf.set_text_color(220, 53, 69)
        pdf.cell(
            30, 6, "AFWIJKING (NOK)", border="B", fill=True, align="C"
        )
      else:
        pdf.set_text_color(25, 135, 84)
        pdf.cell(30, 6, "100% OK", border="B", fill=True, align="C")

      pdf.set_text_color(15, 23, 42)
      pdf.ln(6)

    pdf.ln(8)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_fill_color(241, 245, 249)
    pdf.cell(0, 8, "  2. GEDETAILLEERDE AUDIT DOSSIERS", fill=True, ln=True)
    pdf.ln(4)

  for idx, rit in gefilterde_ritten.iterrows():
    sub_items = gefilterde_items[
        gefilterde_items["audit_id"] == rit["audit_id"]
    ]
    heeft_nok = "NOK" in sub_items["status"].values

    if pdf.get_y() > 210:
      pdf.add_page()

    if heeft_nok:
      pdf.set_fill_color(220, 53, 69)
      status_text = "AFWIJKING VASTGESTELD (NOK)"
    else:
      pdf.set_fill_color(25, 135, 84)
      status_text = "GOEDGEKEURD (100% OK)"

    pdf.set_font("helvetica", "B", 10)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(
        0,
        7,
        f"  AUDIT #{rit['audit_id']}  -  {rit['truck']} ({rit['klant']})  - "
        f" {rit['actie']}   [{status_text}]",
        fill=True,
        ln=True,
    )

    pdf.set_font("helvetica", "", 8)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(
        0,
        6,
        f"  Tijdstip: {rit['timestamp']}    |    Inspecteur: {rit['auditor']}",
        fill=True,
        border="B",
        ln=True,
    )
    pdf.ln(2)

    pdf.set_font("helvetica", "B", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(100, 5, "Controlepunt", border="B")
    pdf.cell(22, 5, "Status", border="B", align="C")
    pdf.cell(68, 5, "Opmerkingen", border="B")
    pdf.ln(5)

    pdf.set_font("helvetica", "", 8)
    for _, it in sub_items.iterrows():
      is_nok_item = it["status"] == "NOK"
      if is_nok_item:
        pdf.set_text_color(220, 53, 69)
        pdf.set_font("helvetica", "B", 8)
      else:
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("helvetica", "", 8)

      pdf.cell(100, 5, str(it["vraag"])[:65], border="B")
      pdf.cell(22, 5, str(it["status"]), border="B", align="C")
      comm_text = str(it["commentaar"]) if pd.notna(it["commentaar"]) else ""
      pdf.cell(68, 5, comm_text[:45], border="B")
      pdf.ln(5)

    pdf.set_text_color(15, 23, 42)
    pdf.ln(2)

    fotos_in_rit = sub_items[
        sub_items["foto_url"].notna() & (sub_items["foto_url"] != "")
    ]
    if len(fotos_in_rit) > 0:
      pdf.set_font("helvetica", "B", 8)
      pdf.set_text_color(15, 23, 42)
      pdf.cell(0, 5, "Bijbehorende Fotobewijzen:", ln=True)

      x_start = 12
      y_start = pdf.get_y()
      foto_w = 42
      foto_h = 32

      for f_idx, (_, f_row) in enumerate(fotos_in_rit.iterrows()):
        if pdf.get_y() + foto_h > 275:
          pdf.add_page()
          y_start = pdf.get_y()

        img_bytes = download_afbeelding_bytes(f_row["foto_url"])
        if img_bytes:
          try:
            x_pos = x_start + (f_idx % 4) * 46
            if f_idx > 0 and f_idx % 4 == 0:
              y_start += foto_h + 8
            pdf.image(
                io.BytesIO(img_bytes),
                x=x_pos,
                y=y_start,
                w=foto_w,
                h=foto_h,
            )
            pdf.set_xy(x_pos, y_start + foto_h + 1)
            pdf.set_font("helvetica", "", 6)
            pdf.cell(
                foto_w,
                4,
                f"Punt: {str(f_row['vraag'])[:25]}",
                align="C",
            )
          except Exception:
            pass

      pdf.set_y(y_start + foto_h + 7)

    pdf.ln(6)

  return bytes(pdf.output())


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
        f" {get_now().strftime('%d-%m-%Y %H:%M')}"
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
            tijd_tag = get_now().strftime("%Y%m%d_%H%M%S")
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
      now_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
      audit_id = int(get_now().strftime("%y%m%d%H%M%S"))
      client = get_supabase()

      if not client:
        st.error(
            "Supabase verbinding niet gevonden. Controleer je secrets"
            " instellingen."
        )
      else:
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

        try:
          client.table("audits").insert({
              "id": audit_id,
              "timestamp": now_str,
              "actie": st.session_state.sel_actie,
              "klant": st.session_state.sel_klant,
              "truck": st.session_state.sel_truck,
              "auditor": huidige_gebruiker,
          }).execute()

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

    try:
      ritten_df["datum"] = pd.to_datetime(ritten_df["timestamp"]).dt.date
    except Exception:
      ritten_df["datum"] = get_now().date()

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

    mask = (
        (ritten_df["datum"] >= van_datum)
        & (ritten_df["datum"] <= tot_datum)
        & (ritten_df["actie"].isin(filter_actie))
        & (ritten_df["klant"].isin(filter_klant))
        & (ritten_df["truck"].isin(filter_truck))
    )
    gefilterde_ritten = ritten_df[mask]

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
      gefilterde_items = compleet_df[
          compleet_df["audit_id"].isin(gefilterde_ritten["audit_id"])
      ]

      ritten_met_nok_aantal = gefilterde_items[
          gefilterde_items["status"] == "NOK"
      ]["audit_id"].nunique()
      ritten_100_ok_aantal = totaal_aantal - ritten_met_nok_aantal
      pct_ok = round((ritten_100_ok_aantal / totaal_aantal) * 100, 1)
      totaal_fotos = gefilterde_items[gefilterde_items["foto_url"] != ""][
          "foto_url"
      ].nunique()

      kpi1, kpi2, kpi3, kpi4 = st.columns(4)
      kpi1.metric("📋 Totaal Audits", f"{totaal_aantal}")
      kpi2.metric("🟢 100% Goedgekeurd", f"{ritten_100_ok_aantal}", f"{pct_ok}%")
      kpi3.metric(
          "🔴 Met Afwijking (NOK)",
          f"{ritten_met_nok_aantal}",
          f"-{round(100 - pct_ok, 1)}%" if ritten_met_nok_aantal > 0 else "0%",
      )
      kpi4.metric("📷 Gemaakte Foto's", f"{totaal_fotos}")

      # --- 3. RAPPORT DOWNLOADS (PDF & CSV) ---
      st.write("---")
      st.subheader("📥 Export & Rapportages")
      down_col1, down_col2, down_col3 = st.columns(3)

      # 1. GROOT MULTI-AUDIT PDF RAPPORT
      with st.spinner("PDF rapport wordt voorbereid..."):
        pdf_bytes = genereer_pdf_rapport(
            gefilterde_ritten,
            gefilterde_items,
            van_datum,
            tot_datum,
            is_enkele_rit=False,
        )

      with down_col1:
        st.download_button(
            label="📑 Download PDF Perioderapport (Alle ritten + foto's)",
            data=pdf_bytes,
            file_name=f"audit_rapport_{van_datum}_tot_{tot_datum}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

      # 2. Management Samenvatting CSV
      samenvatting_rijen = []
      for _, rit_info in gefilterde_ritten.iterrows():
        a_id = rit_info["audit_id"]
        sub_items = gefilterde_items[gefilterde_items["audit_id"] == a_id]
        aantal_ok = len(sub_items[sub_items["status"] == "OK"])
        aantal_nok = len(sub_items[sub_items["status"] == "NOK"])
        heeft_nok = aantal_nok > 0

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

      with down_col2:
        st.download_button(
            label="📄 Download Samenvatting (CSV)",
            data=csv_management,
            file_name=f"audit_samenvatting_{van_datum}_tot_{tot_datum}.csv",
            mime="text/csv",
            use_container_width=True,
        )

      # 3. Volledig Detailrapport CSV
      csv_detail = gefilterde_items.to_csv(index=False).encode("utf-8")
      with down_col3:
        st.download_button(
            label="📋 Download Details (CSV + Fotolinks)",
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

        status_icoon = "🔴" if rit_heeft_nok else "🟢"
        oordeel_label = "⚠️ AFWIJKING" if rit_heeft_nok else "100% OK"
        titel = f"{status_icoon} Audit #{rit['audit_id']} [{oordeel_label}] | {rit['truck']} ({rit['klant']}) - {rit['actie']} om {rit['timestamp']}"

        with st.expander(titel):
          col_exp1, col_exp2 = st.columns([3, 1])
          with col_exp1:
            st.write(f"**Inspecteur:** {rit['auditor']}")
          with col_exp2:
            enkele_rit_df = gefilterde_ritten[
                gefilterde_ritten["audit_id"] == rit["audit_id"]
            ]
            enkele_items_df = gefilterde_items[
                gefilterde_items["audit_id"] == rit["audit_id"]
            ]
            pdf_enkel = genereer_pdf_rapport(
                enkele_rit_df,
                enkele_items_df,
                van_datum,
                tot_datum,
                is_enkele_rit=True,
            )
            st.download_button(
                label="📥 Download PDF van deze rit",
                data=pdf_enkel,
                file_name=f"Audit_Dossier_{rit['audit_id']}_{rit['truck']}.pdf",
                mime="application/pdf",
                key=f"dl_pdf_{rit['audit_id']}",
                use_container_width=True,
            )

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
