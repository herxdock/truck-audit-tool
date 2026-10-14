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
        border: 6px solid #1e293b !important;          /* 6 PIXELS DIKKE RAND */
        border-radius: 24px !important;
        background-color: #ffffff !important;
        padding: 24px 20px !important;
        margin-top: 15px !important;
        margin-bottom: 45px !important;                /* Grote witruimte tussen blokken */
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.22) !important; /* Duidelijke schaduw */
    }

    /* Vraag titel als een opvallende donkere kopbalk */
    .vraag-titel {
        font-size: 28px !important;
        font-weight: 900 !important;
        color: #ffffff !important;
        background-color: #1e293b !important;          /* Donkere achtergrond */
        padding: 14px 18px !important;
        border-radius: 14px !important;
        margin-bottom: 20px !important;
        line-height: 1.3 !important;
    }

    /* ==========================================
       2. GROTE TOUCHKNOPPEN
       ========================================== */
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

    /* Geselecteerde standaard knop (Blauw) */
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

    /* ==========================================
       3. OK & NOK KNOPPEN
       ========================================== */
    /* OK Knop: KNALGROEN */
    div[class*="st-key-btn_ok_"] button[kind="primary"] {
        background-color: #198754 !important;
        border: 4px solid #0f5132 !important;
    }
    div[class*="st-key-btn_ok_"] button[kind="primary"] p {
        color: #ffffff !important;
    }

    /* NOK Knop: KNALROOD */
    div[class*="st-key-btn_nok_"] button[kind="primary"] {
        background-color: #dc3545 !important;
        border: 4px solid #842029 !important;
    }
    div[class*="st-key-btn_nok_"] button[kind="primary"] p {
        color: #ffffff !important;
    }

    /* ==========================================
       4. INVOER & CAMERA
       ========================================== */
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

FOTO_MAP = "audit_fotos"
os.makedirs(FOTO_MAP, exist_ok=True)
DB_PATH = "audit_systeem.db"

# ==========================================
# DATABASE SETUP
# ==========================================
def get_db():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  with get_db() as conn:
    c = conn.cursor()
    c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
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
      # Elk controlepunt in een 6px dik omlijnd blok
      with st.container(border=True):
        st.markdown(
            f"<div class='vraag-titel'>{vraag}</div>", unsafe_allow_html=True
        )

        huidige_status = st.session_state.get(f"status_{i}", "OK")

        # DIKKE OK EN NOK KNOPPEN
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

        # COMMENTAARVAK
        comment = st.text_input(
            "Opmerking (optioneel):",
            key=f"comm_{i}",
            placeholder="Typ hier eventuele opmerkingen of schades...",
        )

        # OPTIONELE CAMERA KNOP ('Take picture')
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
            # Veilige naam maken zonder vreemde tekens of schuine strepen
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
            foto_pad = os.path.join(FOTO_MAP, foto_bestandsnaam)

            # GARANDEER dat de map bestaat vlak voor het wegschrijven:
            os.makedirs(FOTO_MAP, exist_ok=True)

            with open(foto_pad, "wb") as f:
              f.write(foto.getbuffer())

            st.session_state[f"saved_foto_{i}"] = foto_bestandsnaam
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
        })

    # OPSLAAN KNOP
    st.write("<br>", unsafe_allow_html=True)
    if st.button(
        "💾 AUDIT VOLTOOIEN EN OPSLAAN",
        type="primary",
        use_container_width=True,
    ):
      with get_db() as conn:
        c = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """
                    INSERT INTO audits (timestamp, actie, klant, truck, auditor) 
                    VALUES (?, ?, ?, ?, ?)
                """,
            (
                now_str,
                st.session_state.sel_actie,
                st.session_state.sel_klant,
                st.session_state.sel_truck,
                huidige_gebruiker,
            ),
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

      st.success(f"✅ Audit #{audit_id} succesvol opgeslagen!")

      # Reset alle velden voor de volgende rit
      st.session_state.sel_actie = None
      st.session_state.sel_klant = None
      st.session_state.sel_truck = None
      for i in range(len(actieve_vragen)):
        st.session_state.pop(f"status_{i}", None)
        st.session_state.pop(f"comm_{i}", None)
        st.session_state.pop(f"show_cam_{i}", None)
        st.session_state.pop(f"saved_foto_{i}", None)
        st.session_state.pop(f"foto_{i}", None)
      st.rerun()

# ==========================================
# ONDERDEEL 2: HISTORIE (ALLEEN ADMIN)
# ==========================================
elif menu == "📊 Historie & Foto's" and is_admin:
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
  st.caption("Beheer trucks, klanten, koppelingen en controlepunten.")

  tab1, tab2, tab3, tab4 = st.tabs([
      "🔗 Klanten & Trucks Koppelen",
      "🏢 Klanten",
      "🚛 Trucks",
      "❓ Vragen per Actie",
  ])

  # --- TAB 1: KOPPELINGEN ---
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

  # --- TAB 2: KLANTEN ---
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

  # --- TAB 3: TRUCKS ---
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

  # --- TAB 4: VRAGEN PER ACTIE (LOAD / UNLOAD) ---
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
