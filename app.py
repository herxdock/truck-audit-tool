from datetime import datetime
import io
import json
import os
import sqlite3
import zipfile
import pandas as pd
import streamlit as st

# Pagina instellingen (breed voor tablet)
st.set_page_config(
    page_title="Truck Audit Systeem", page_icon="🚛", layout="wide"
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
standaard_vragen = [
    "1. Algemene laadkwaliteit",
    "2. Zichtbare schade aan goederen/trailer",
    "3. Zekering / Spandraad / Securing beams",
    "4. Netheid van de laadruimte",
    "5. Correcte documentatie / Vrachtbrief",
]
standaard_trucks = [
    "Truck 01",
    "Truck 02",
    "Truck 03",
    "Truck 04",
    "Truck 05",
    "Truck 06",
]
standaard_klanten = ["BMW", "Toyota", "Scania", "Grieshaber", "TS-Lux"]

# Standaard koppeling tussen klant en trucks
standaard_klant_trucks = {
    "BMW": ["Truck 01", "Truck 02"],
    "Toyota": ["Truck 02", "Truck 03"],
    "Scania": ["Truck 03", "Truck 04"],
    "Grieshaber": ["Truck 04", "Truck 05"],
    "TS-Lux": ["Truck 01", "Truck 05", "Truck 06"],
}

vragen_lijst = get_setting("vragen", standaard_vragen)
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
  col_l, col_center, col_r = st.columns([1, 1.8, 1])
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

  # Session state voor selecties initialiseren
  if "sel_actie" not in st.session_state:
    st.session_state.sel_actie = None
  if "sel_klant" not in st.session_state:
    st.session_state.sel_klant = None
  if "sel_truck" not in st.session_state:
    st.session_state.sel_truck = None

  # Knop om tussentijds te resetten
  col_head1, col_head2 = st.columns([3, 1])
  with col_head1:
    st.caption(
        f"Inspecteur: **{huidige_gebruiker}** |"
        f" {datetime.now().strftime('%d-%m-%Y %H:%M')}"
    )
  with col_head2:
    if st.session_state.sel_actie is not None:
      if st.button("🔄 Selectie Resetten", use_container_width=True):
        st.session_state.sel_actie = None
        st.session_state.sel_klant = None
        st.session_state.sel_truck = None
        st.rerun()

  # STAP 1: GROTE ACTIE KNOPPEN (LOAD / UNLOAD)
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

  # STAP 2: GROTE KLANT KNOPPEN (Alleen zichtbaar als actie is gekozen)
  if st.session_state.sel_actie:
    st.write("---")
    st.subheader(f"2. Kies Klant voor {st.session_state.sel_actie}")

    # Toon klanten in rijen van 3 grote knoppen
    kolommen_per_rij = 3
    for i in range(0, len(klanten_lijst), kolommen_per_rij):
      cols = st.columns(kolommen_per_rij)
      for j, klant_naam in enumerate(klanten_lijst[i : i + kolommen_per_rij]):
        with cols[j]:
          is_active = st.session_state.sel_klant == klant_naam
          if st.button(
              klant_naam,
              key=f"btn_k_{klant_naam}",
              use_container_width=True,
              type="primary" if is_active else "secondary",
          ):
            st.session_state.sel_klant = klant_naam
            # Reset truckkeuze als de klant wisselt
            st.session_state.sel_truck = None
            st.rerun()

  # STAP 3: GEFILTERDE TRUCK KEUZE (Alleen zichtbaar als klant is gekozen)
  if st.session_state.sel_klant:
    st.write("---")
    st.subheader(f"3. Kies Truck voor {st.session_state.sel_klant}")

    # Haal alleen trucks op die aan DEZE klant gekoppeld zijn
    gekoppelde_trucks = klant_trucks_map.get(
        st.session_state.sel_klant, trucks_lijst
    )

    if not gekoppelde_trucks:
      st.warning(
          f"⚠️ Er zijn in het beheerpaneel nog geen trucks gekoppeld aan"
          f" '{st.session_state.sel_klant}'."
      )
    else:
      kolommen_trucks = 3
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

  # STAP 4: DE VRAGENLIJST & CAMERA (Zichtbaar zodra alles gekozen is)
  if (
      st.session_state.sel_actie
      and st.session_state.sel_klant
      and st.session_state.sel_truck
  ):
    st.write("---")
    st.success(
        f"Geselecteerd: **{st.session_state.sel_actie}** | Klant:"
        f" **{st.session_state.sel_klant}** | Truck:"
        f" **{st.session_state.sel_truck}**"
    )
    st.subheader("4. Controle & Foto's")

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
        safe_truck = st.session_state.sel_truck.replace(" ", "_")
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
      # Reset selecties voor de volgende rit
      st.session_state.sel_actie = None
      st.session_state.sel_klant = None
      st.session_state.sel_truck = None
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
      "❓ Vragen",
  ])

  # --- TAB 1: KOPPELINGEN TUSSEN KLANT EN TRUCKS ---
  with tab1:
    st.subheader("Koppel vrachtwagens aan een specifieke klant")
    st.caption(
        "Alleen de trucks die je hier selecteert worden zichtbaar wanneer deze"
        " klant wordt gekozen."
    )

    gekozen_klant = st.selectbox("Kies Klant om te configureren", klanten_lijst)
    huidige_gekoppelde = klant_trucks_map.get(gekozen_klant, [])

    geselecteerde_trucks = st.multiselect(
        f"Beschikbare trucks voor '{gekozen_klant}':",
        options=trucks_lijst,
        default=[t for t in huidige_gekoppelde if t in trucks_lijst],
    )

    if st.button("💾 Koppeling Opslaan voor deze klant", type="primary"):
      klant_trucks_map[gekozen_klant] = geselecteerde_trucks
      set_setting("klant_trucks", klant_trucks_map)
      st.success(
          f"Instellingen opgeslagen! {len(geselecteerde_trucks)} trucks"
          f" gekoppeld aan {gekozen_klant}."
      )
      st.rerun()

  # --- TAB 2: KLANTEN BEHEREN ---
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

  # --- TAB 3: TRUCKS BEHEREN ---
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

  # --- TAB 4: VRAGEN BEHEREN ---
  with tab4:
    nieuwe_vraag = st.text_input("Nieuw controlepunt toevoegen")
    if st.button("Voeg vraag toe"):
      if nieuwe_vraag and nieuwe_vraag not in vragen_lijst:
        vragen_lijst.append(nieuwe_vraag)
        set_setting("vragen", vragen_lijst)
        st.rerun()

    del_vraag = st.selectbox("Verwijder een vraag", ["---"] + vragen_lijst)
    if st.button("Verwijder vraag"):
      if del_vraag != "---":
        vragen_lijst.remove(del_vraag)
        set_setting("vragen", vragen_lijst)
        st.rerun()
    st.write("Actieve vragen:", vragen_lijst)
