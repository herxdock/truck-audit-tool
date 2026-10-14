from datetime import datetime
import io
import json
import os
import sqlite3
import zipfile
import pandas as pd
import streamlit as st

# Pagina instellingen
st.set_page_config(
    page_title="Truck Audit Systeem", page_icon="🚛", layout="wide"
)

FOTO_MAP = "audit_fotos"
os.makedirs(FOTO_MAP, exist_ok=True)
DB_PATH = "audit_systeem.db"

# ==========================================
# DATABASE SETUP (ALLEEN VOOR AUDITS & CONFIG)
# ==========================================
def get_db():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  with get_db() as conn:
    c = conn.cursor()
    # Instellingen tabel (trucks, klanten, vragen)
    c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
    # Audits tabel
    c.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                actie TEXT,
                klant TEXT,
                truck TEXT,
                auditor TEXT
            )
        """)
    # Controlepunten tabel
    c.execute("""
            CREATE TABLE IF NOT EXISTS audit_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id INTEGER,
                vraag TEXT,
                status TEXT,
                commentaar TEXT,
                foto_pad TEXT,
                FOREIGN KEY(audit_id) REFERENCES audits(id)
            )
        """)
    conn.commit()


init_db()


# Helper functies voor instellingen
def get_setting(key, default):
  with get_db() as conn:
    row = (
        conn.cursor()
        .execute("SELECT value FROM settings WHERE key = ?", (key,))
        .fetchone()
    )
    if row:
      return json.loads(row["value"])
    return default


def set_setting(key, value):
  with get_db() as conn:
    conn.cursor().execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, json.dumps(value)),
    )
    conn.commit()


# Standaard opties
standaard_vragen = [
    "1. Algemene laadkwaliteit",
    "2. Zichtbare schade aan goederen/trailer",
    "3. Zekering / Spandraad / Securing beams",
    "4. Netheid van de laadruimte",
    "5. Correcte documentatie / Vrachtbrief",
]
standaard_trucks = ["Truck 01", "Truck 02", "Truck 03", "Truck 04"]
standaard_klanten = ["BMW", "Toyota", "Scania", "Grieshaber", "TS-Lux"]

vragen_lijst = get_setting("vragen", standaard_vragen)
trucks_lijst = get_setting("trucks", standaard_trucks)
klanten_lijst = get_setting("klanten", standaard_klanten)


# ==========================================
# INLOGGEN VIA STREAMLIT SECRETS
# ==========================================
def verify_login(username, password):
  """Controleert inloggegevens direct via st.secrets (ondersteunt 'auditors' en negeert hoofdletters)."""
  user_clean = username.strip().lower()
  pass_clean = password.strip()

  # 1. Controleer admins
  if "admins" in st.secrets:
    for admin_user, admin_pass in st.secrets["admins"].items():
      if (
          str(admin_user).lower() == user_clean
          and str(admin_pass) == pass_clean
      ):
        return {"username": str(admin_user), "role": "admin"}

  # 2. Controleer auditors (of inspecteurs)
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

# Inlogscherm tonen indien niet ingelogd
if not st.session_state.logged_in:
  col_l, col_center, col_r = st.columns([1, 1.8, 1])
  with col_center:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.title("🔐 Login Truck Audit")
    st.caption("Voer uw gebruikersnaam en wachtwoord in.")

    with st.form("login_form"):
      user_input = st.text_input("Gebruikersnaam")
      pass_input = st.text_input("Wachtwoord", type="password")
      submit = st.form_submit_button("Inloggen", use_container_width=True)

      if submit:
        user_info = verify_login(user_input, pass_input)
        if user_info:
          st.session_state.logged_in = True
          st.session_state.user = user_info
          st.success("Succesvol ingelogd!")
          st.rerun()
        else:
          st.error("Onjuiste gebruikersnaam of wachtwoord.")
  st.stop()


# ==========================================
# HOOFDMENU (NA SUCCESVOLLE LOGIN)
# ==========================================
huidige_gebruiker = st.session_state.user["username"]
is_admin = st.session_state.user["role"] == "admin"

st.sidebar.markdown(f"### 👤 Ingelogd: `{huidige_gebruiker}`")
st.sidebar.caption(f"Rol: {'Beheerder' if is_admin else 'Inspecteur'}")

if st.sidebar.button("🚪 Uitloggen", use_container_width=True):
  st.session_state.logged_in = False
  st.session_state.user = None
  st.rerun()

st.sidebar.write("---")

menu_opties = ["📋 Nieuwe Audit", "📊 Historie & Foto's"]
if is_admin:
  menu_opties.append("⚙️ Beheer & Instellingen")

menu = st.sidebar.radio("Navigatie", menu_opties)


# ==========================================
# ONDERDEEL 1: NIEUWE AUDIT
# ==========================================
if menu == "📋 Nieuwe Audit":
  st.title("📋 Nieuwe Truck Audit")
  st.caption(
      f"Datum: {datetime.now().strftime('%d-%m-%Y %H:%M')} | Inspecteur:"
      f" {huidige_gebruiker}"
  )

  col1, col2, col3 = st.columns(3)
  with col1:
    actie = st.selectbox("Actie", ["Load (Laden)", "Unload (Lossen)"])
  with col2:
    klant = st.selectbox("Klant", klanten_lijst)
  with col3:
    truck = st.selectbox("Vrachtwagen", trucks_lijst)

  st.write("---")
  st.subheader("Controlepunten & Foto's")

  antwoorden = []
  for i, vraag in enumerate(vragen_lijst):
    st.markdown(f"#### {vraag}")
    col_a, col_b = st.columns([1, 2])
    with col_a:
      status = st.radio(
          "Status",
          ["OK", "NOK"],
          key=f"status_{i}",
          horizontal=True,
          index=0,
      )
    with col_b:
      comment = st.text_input("Opmerking (optioneel)", key=f"comm_{i}")

    foto = st.camera_input(f"Foto voor punt {i+1}", key=f"foto_{i}")
    foto_bestandsnaam = ""

    if foto is not None:
      tijd_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
      safe_truck = truck.replace(" ", "_")
      foto_bestandsnaam = f"{safe_truck}_v{i+1}_{tijd_tag}.png"
      foto_pad = os.path.join(FOTO_MAP, foto_bestandsnaam)
      with open(foto_pad, "wb") as f:
        f.write(foto.getbuffer())

    antwoorden.append({
        "vraag": vraag,
        "status": status,
        "commentaar": comment,
        "foto_pad": foto_bestandsnaam,
    })
    st.write("---")

  if st.button("💾 Audit Opslaan", type="primary", use_container_width=True):
    with get_db() as conn:
      c = conn.cursor()
      now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      c.execute(
          "INSERT INTO audits (timestamp, actie, klant, truck, auditor) VALUES"
          " (?, ?, ?, ?, ?)",
          (now_str, actie, klant, truck, huidige_gebruiker),
      )
      audit_id = c.lastrowid

      for item in antwoorden:
        c.execute(
            """
                    INSERT INTO audit_items (audit_id, vraag, status, commentaar, foto_pad)
                    VALUES (?, ?, ?, ?, ?)
                """,
            (
                audit_id,
                item["vraag"],
                item["status"],
                item["commentaar"],
                item["foto_pad"],
            ),
        )
      conn.commit()

    st.success(
        f"✅ Audit #{audit_id} succesvol opgeslagen door {huidige_gebruiker}!"
    )


# ==========================================
# ONDERDEEL 2: HISTORIE & EXPORT
# ==========================================
elif menu == "📊 Historie & Foto's":
  st.title("📊 Historisch Overzicht & Downloads")

  with get_db() as conn:
    audits_df = pd.read_sql_query(
        "SELECT * FROM audits ORDER BY id DESC", conn
    )

  if audits_df.empty:
    st.info("Er zijn nog geen audits geregistreerd.")
  else:
    col1, col2 = st.columns(2)
    with col1:
      filter_truck = st.multiselect(
          "Filter op Truck",
          options=audits_df["truck"].unique(),
          default=audits_df["truck"].unique(),
      )
    with col2:
      filter_klant = st.multiselect(
          "Filter op Klant",
          options=audits_df["klant"].unique(),
          default=audits_df["klant"].unique(),
      )

    gefilterde_audits = audits_df[
        audits_df["truck"].isin(filter_truck)
        & audits_df["klant"].isin(filter_klant)
    ]

    st.subheader("📥 Export Opties")
    col_d1, col_d2 = st.columns(2)

    with get_db() as conn:
      query_compleet = """
                SELECT a.id as audit_id, a.timestamp, a.actie, a.klant, a.truck, a.auditor,
                       i.vraag, i.status, i.commentaar, i.foto_pad
                FROM audits a
                JOIN audit_items i ON a.id = i.audit_id
                ORDER BY a.id DESC
            """
      compleet_df = pd.read_sql_query(query_compleet, conn)

    csv_data = compleet_df.to_csv(index=False).encode("utf-8")
    with col_d1:
      st.download_button(
          label="📄 Download Data als CSV (Excel)",
          data=csv_data,
          file_name=f"audits_{datetime.now().strftime('%Y%m%d')}.csv",
          mime="text/csv",
          use_container_width=True,
      )

    with col_d2:
      zip_buffer = io.BytesIO()
      with zipfile.ZipFile(
          zip_buffer, "w", zipfile.ZIP_DEFLATED
      ) as zip_bestand:
        zip_bestand.writestr("audit_data.csv", csv_data)
        for bestandsnaam in os.listdir(FOTO_MAP):
          pad = os.path.join(FOTO_MAP, bestandsnaam)
          if os.path.isfile(pad):
            zip_bestand.write(pad, arcname=os.path.join("fotos", bestandsnaam))

      zip_buffer.seek(0)
      st.download_button(
          label="📦 Download Alles als ZIP (Inclusief foto's)",
          data=zip_buffer,
          file_name=f"audits_compleet_{datetime.now().strftime('%Y%m%d')}.zip",
          mime="application/zip",
          use_container_width=True,
      )

    st.write("---")
    st.subheader("Rittenoverzicht")

    for _, audit in gefilterde_audits.iterrows():
      titel = f"Audit #{audit['id']} | {audit['truck']} ({audit['klant']}) - {audit['actie']} om {audit['timestamp']}"
      with st.expander(titel):
        st.write(f"**Inspecteur:** {audit['auditor']}")

        with get_db() as conn:
          items = conn.cursor().execute(
              "SELECT * FROM audit_items WHERE audit_id = ?", (audit["id"],)
          ).fetchall()

        for it in items:
          kleur = "🟢" if it["status"] == "OK" else "🔴"
          st.markdown(
              f"**{kleur} {it['vraag']}** — Status: **{it['status']}**"
          )
          if it["commentaar"]:
            st.write(f"💬 Opmerking: *{it['commentaar']}*")
          if it["foto_pad"]:
            foto_locatie = os.path.join(FOTO_MAP, it["foto_pad"])
            if os.path.exists(foto_locatie):
              st.image(
                  foto_locatie,
                  caption=f"Foto: {it['foto_pad']}",
                  width=350,
              )
          st.write("---")


# ==========================================
# ONDERDEEL 3: BEHEER & INSTELLINGEN (ADMIN)
# ==========================================
elif menu == "⚙️ Beheer & Instellingen" and is_admin:
  st.title("⚙️ Beheerpaneel")
  st.caption("Beheer vrachtwagens, klanten en controlepunten.")

  tab1, tab2, tab3 = st.tabs(["🚛 Trucks", "🏢 Klanten", "❓ Vragen"])

  # --- TAB 1: TRUCKS ---
  with tab1:
    huidige_trucks = get_setting("trucks", standaard_trucks)
    nieuwe_truck = st.text_input("Nieuwe vrachtwagen toevoegen")
    if st.button("Voeg truck toe"):
      if nieuwe_truck and nieuwe_truck not in huidige_trucks:
        huidige_trucks.append(nieuwe_truck)
        set_setting("trucks", huidige_trucks)
        st.rerun()

    del_truck = st.selectbox("Verwijder een truck", ["---"] + huidige_trucks)
    if st.button("Verwijder truck"):
      if del_truck != "---":
        huidige_trucks.remove(del_truck)
        set_setting("trucks", huidige_trucks)
        st.rerun()
    st.write("Actieve lijst:", huidige_trucks)

  # --- TAB 2: KLANTEN ---
  with tab2:
    huidige_klanten = get_setting("klanten", standaard_klanten)
    nieuwe_klant = st.text_input("Nieuwe klant toevoegen")
    if st.button("Voeg klant toe"):
      if nieuwe_klant and nieuwe_klant not in huidige_klanten:
        huidige_klanten.append(nieuwe_klant)
        set_setting("klanten", huidige_klanten)
        st.rerun()

    del_klant = st.selectbox("Verwijder een klant", ["---"] + huidige_klanten)
    if st.button("Verwijder klant"):
      if del_klant != "---":
        huidige_klanten.remove(del_klant)
        set_setting("klanten", huidige_klanten)
        st.rerun()
    st.write("Actieve lijst:", huidige_klanten)

  # --- TAB 3: VRAGEN ---
  with tab3:
    huidige_vragen = get_setting("vragen", standaard_vragen)
    nieuwe_vraag = st.text_input("Nieuw controlepunt toevoegen")
    if st.button("Voeg vraag toe"):
      if nieuwe_vraag and nieuwe_vraag not in huidige_vragen:
        huidige_vragen.append(nieuwe_vraag)
        set_setting("vragen", huidige_vragen)
        st.rerun()

    del_vraag = st.selectbox("Verwijder een vraag", ["---"] + huidige_vragen)
    if st.button("Verwijder vraag"):
      if del_vraag != "---":
        huidige_vragen.remove(del_vraag)
        set_setting("vragen", huidige_vragen)
        st.rerun()
    st.write("Actieve lijst:", huidige_vragen)
