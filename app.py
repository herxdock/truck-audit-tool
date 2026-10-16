from streamlit_back_camera_input import back_camera_input
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


# ==========================================
# VERWIJDER-FUNCTIE (audit + items + foto's + log)
# ==========================================
def verwijder_audit_volledig(audit_id, uitgevoerd_door, opmerking=""):
  """
  Verwijdert een audit + items + bijhorende storage-bestanden.
  Logt de actie in de deletion_log tabel.
  Retourneert (success: bool, message: str, stats: dict).
  """
  client = get_supabase()
  if not client:
    return False, "Geen Supabase verbinding.", {}

  stats = {
      "aantal_items": 0,
      "aantal_fotos": 0,
      "foto_paden": [],
      "klant": None,
      "truck": None,
      "auditor": None,
  }

  try:
    # 1. Audit header ophalen (voor log + referentie)
    audit_res = (
        client.table("audits")
        .select("*")
        .eq("id", audit_id)
        .limit(1)
        .execute()
    )
    if not audit_res.data:
      return False, f"Audit #{audit_id} niet gevonden.", stats

    audit_row = audit_res.data[0]
    stats["klant"] = audit_row.get("klant")
    stats["truck"] = audit_row.get("truck")
    stats["auditor"] = audit_row.get("auditor")

    # 2. Items ophalen (om foto_paden te kennen)
    items_res = (
        client.table("audit_items")
        .select("id, foto_url")
        .eq("audit_id", audit_id)
        .execute()
    )
    items = items_res.data or []
    stats["aantal_items"] = len(items)

    # 3. Foto-paden uit URL's halen
    foto_paden = []
    for it in items:
      url = it.get("foto_url") or ""
      if url and "audit-fotos/" in url:
        pad = url.split("audit-fotos/")[-1].split("?")[0]
        if pad:
          foto_paden.append(pad)

    stats["foto_paden"] = foto_paden
    stats["aantal_fotos"] = len(foto_paden)

    # 4. Storage cleanup (best-effort, faalt niet de hele delete)
    if foto_paden:
      try:
        client.storage.from_("audit-fotos").remove(foto_paden)
      except Exception as e_storage:
        st.warning(f"⚠️ Storage cleanup deels gefaald: {e_storage}")

    # 5. Items verwijderen
    client.table("audit_items").delete().eq("audit_id", audit_id).execute()

    # 6. Audit verwijderen
    client.table("audits").delete().eq("id", audit_id).execute()

    # 7. Loggen
    try:
      client.table("deletion_log").insert({
          "audit_id": audit_id,
          "klant": stats["klant"],
          "truck": stats["truck"],
          "auditor": stats["auditor"],
          "uitgevoerd_door": uitgevoerd_door,
          "aantal_items": stats["aantal_items"],
          "aantal_fotos": stats["aantal_fotos"],
          "foto_paden": stats["foto_paden"],
          "opmerking": opmerking or "",
      }).execute()
    except Exception as e_log:
      st.warning(
          f"⚠️ Log wegschrijven faalde (audit is wel verwijderd): {e_log}"
      )

    return True, f"Audit #{audit_id} definitief verwijderd.", stats

  except Exception as e:
    return False, f"Fout bij verwijderen: {e}", stats


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
        # Ook alle vraag-gerelateerde state opruimen
        for k in list(st.session_state.keys()):
          if (
              k.startswith("status_")
              or k.startswith("comm_")
              or k.startswith("show_cam_")
              or k.startswith("saved_foto_")
              or k.startswith("saved_bytes_")
              or k.startswith("foto_")
          ):
            del st.session_state[k]
        st.rerun()

  # STAP 1: GROTE ACTIE KNOPPEN
  st.subheader("1. Kies Actie")
  c1, c2 = st.columns(2)
  with c1:
    is_unload = st.session_state.sel_actie == "Unload"
    if st.button(
        "🚚 UNLOAD (Lossen)",
        use_container_width=True,
        type="primary" if is_unload else "secondary",
    ):
      st.session_state.sel_actie = "Unload"
      st.rerun()
  with c2:
    is_load = st.session_state.sel_actie == "Load"
    if st.button(
        "📦 LOAD (Laden)",
        use_container_width=True,
        type="primary" if is_load else "secondary",
    ):
      st.session_state.sel_actie = "Load"
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

        foto_b
