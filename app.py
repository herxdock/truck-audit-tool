import io
import json
import os
import sqlite3
import zipfile
from datetime import datetime
import pandas as pd
import streamlit as st

# Pagina instellingen (geschikt voor tablet)
st.set_page_config(page_title="Truck Audit Systeem", page_icon="🚛", layout="wide")

FOTO_MAP = "audit_fotos"
os.makedirs(FOTO_MAP, exist_ok=True)
DB_PATH = "audit_systeem.db"

# ==========================================
# DATABASE & CONFIGURATIE SETUP
# ==========================================
def get_db():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  with get_db() as conn:
    c = conn.cursor()
    # Tabel voor configuratie (trucks, klanten, vragen)
    c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
    # Tabel voor audits
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
    # Tabel voor individuele controlepunten per audit
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


# Standaardwaarden als het systeem nieuw is
standaard_vragen = [
    "1. Algemene laadkwaliteit",
    "2. Zichtbare schade aan goederen/trailer",
    "3. Zekering / Spandraad / Securing beams",
    "4. Netheid van de laadruimte",
    "5. Correcte documentatie / Vrachtbrief",
]
standaard_trucks = ["Truck 01", "Truck 02", "Truck 03", "Truck 04"]
standaard_klanten = ["BMW", "Toyota", "Scania", "Grieshaber", "TS-Lux"]

# Haal live instellingen op uit de database
vragen_lijst = get_setting("vragen", standaard_vragen)
trucks_lijst = get_setting("trucks", standaard_trucks)
klanten_lijst = get_setting("klanten", standaard_klanten)

# ==========================================
# NAVIGATIE IN DE ZIJBALK
# ==========================================
st.sidebar.title("🚛 Audit Navigatie")
menu = st.sidebar.radio(
    "Kies een onderdeel:",
    ["📋 Nieuwe Audit", "📊 Historie & Foto's", "⚙️ Beheer & Instellingen"],
)


# ==========================================
# ONDERDEEL 1: NIEUWE AUDIT UITVOEREN
# ==========================================
if menu == "📋 Nieuwe Audit":
  st.title("📋 Nieuwe Truck Audit")
  st.caption(
      f"Datum/tijd: {datetime.now().strftime('%d-%m-%Y %H:%M')} | Tablet"
      " Inspectieformulier"
  )

  col1, col2, col3 = st.columns(3)
  with col1:
    actie = st.selectbox("Actie", ["Load (Laden)", "Unload (Lossen)"])
  with col2:
    klant = st.selectbox("Klant", klanten_lijst)
  with col3:
    truck = st.selectbox("Vrachtwagen", trucks_lijst)

  auditor_naam = st.text_input("Naam inspecteur", value="Kwaliteitscontroleur")

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

    # Camera widget
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
          (now_str, actie, klant, truck, auditor_naam),
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
        f"✅ Audit #{audit_id} succesvol opgeslagen! Alle gegevens en foto's"
        " zijn veilig vastgelegd."
    )


# ==========================================
# ONDERDEEL 2: HISTORIE RAADPLEGEN & EXPORT
# ==========================================
elif menu == "📊 Historie & Foto's":
  st.title("📊 Historisch Overzicht & Downloads")

  with get_db() as conn:
    audits_df = pd.read_sql_query(
        "SELECT * FROM audits ORDER BY id DESC", conn
    )

  if audits_df.empty:
    st.info("Er zijn nog geen audits opgeslagen.")
  else:
    # Filters
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

    # --- DOWNLOAD SECTIE (CSV + ZIP MET FOTO'S) ---
    st.subheader("📥 Export Opties")
    col_d1, col_d2 = st.columns(2)

    # 1. Download CSV
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
          file_name=f"audits_export_{datetime.now().strftime('%Y%m%d')}.csv",
          mime="text/csv",
          use_container_width=True,
      )

    # 2. Download ZIP met CSV + alle foto's
    with col_d2:
      zip_buffer = io.BytesIO()
      with zipfile.ZipFile(
          zip_buffer, "w", zipfile.ZIP_DEFLATED
      ) as zip_bestand:
        # Voeg CSV toe aan ZIP
        zip_bestand.writestr("audit_data.csv", csv_data)
        # Voeg alle foto's toe
        for bestandsnaam in os.listdir(FOTO_MAP):
          pad = os.path.join(FOTO_MAP, bestandsnaam)
          if os.path.isfile(pad):
            zip_bestand.write(pad, arcname=os.path.join("fotos", bestandsnaam))

      zip_buffer.seek(0)
      st.download_button(
          label="📦 Download Alles als ZIP (Inclusief alle foto's)",
          data=zip_buffer,
          file_name=f"audit_compleet_met_fotos_{datetime.now().strftime('%Y%m%d')}.zip",
          mime="application/zip",
          use_container_width=True,
      )

    st.write("---")
    st.subheader("Geauditeerde Ritten")

    # Toon elke audit in een uitklapbare tegel
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
# ONDERDEEL 3: BEHEER & INSTELLINGEN
# ==========================================
elif menu == "⚙️ Beheer & Instellingen":
  st.title("⚙️ Beheerpaneel")
  st.caption("Voeg hier trucks, klanten of vragen toe en pas de lijst aan.")

  # Eenvoudige beveiliging van het beheer
  admin_pass = st.text_input(
      "Voer het beheer-wachtwoord in om instellingen te wijzigen",
      type="password",
  )

  if admin_pass == "admin123":
    st.success("Toegang verleend tot configuratie.")

    tab1, tab2, tab3 = st.tabs(["🚛 Trucks", "🏢 Klanten", "❓ Auditvragen"])

    # --- TAB 1: TRUCKS BEHEREN ---
    with tab1:
      st.subheader("Lijst met vrachtwagens")
      huidige_trucks = get_setting("trucks", standaard_trucks)

      nieuwe_truck = st.text_input("Nieuwe vrachtwagen toevoegen")
      if st.button("Voeg vrachtwagen toe"):
        if nieuwe_truck and nieuwe_truck not in huidige_trucks:
          huidige_trucks.append(nieuwe_truck)
          set_setting("trucks", huidige_trucks)
          st.rerun()

      te_verwijderen_truck = st.selectbox(
          "Verwijder een truck", ["---"] + huidige_trucks
      )
      if st.button("Verwijder truck"):
        if te_verwijderen_truck != "---":
          huidige_trucks.remove(te_verwijderen_truck)
          set_setting("trucks", huidige_trucks)
          st.rerun()

      st.write("Huidige lijst:", huidige_trucks)

    # --- TAB 2: KLANTEN BEHEREN ---
    with tab2:
      st.subheader("Lijst met klanten")
      huidige_klanten = get_setting("klanten", standaard_klanten)

      nieuwe_klant = st.text_input("Nieuwe klant toevoegen")
      if st.button("Voeg klant toe"):
        if nieuwe_klant and nieuwe_klant not in huidige_klanten:
          huidige_klanten.append(nieuwe_klant)
          set_setting("klanten", huidige_klanten)
          st.rerun()

      te_verwijderen_klant = st.selectbox(
          "Verwijder een klant", ["---"] + huidige_klanten
      )
      if st.button("Verwijder klant"):
        if te_verwijderen_klant != "---":
          huidige_klanten.remove(te_verwijderen_klant)
          set_setting("klanten", huidige_klanten)
          st.rerun()

      st.write("Huidige lijst:", huidige_klanten)

    # --- TAB 3: VRAGEN BEHEREN ---
    with tab3:
      st.subheader("Vragenlijst / Inspectiepunten")
      huidige_vragen = get_setting("vragen", standaard_vragen)

      nieuwe_vraag = st.text_input("Nieuw controlepunt toevoegen")
      if st.button("Voeg vraag toe"):
        if nieuwe_vraag and nieuwe_vraag not in huidige_vragen:
          huidige_vragen.append(nieuwe_vraag)
          set_setting("vragen", huidige_vragen)
          st.rerun()

      te_verwijderen_vraag = st.selectbox(
          "Verwijder een vraag", ["---"] + huidige_vragen
      )
      if st.button("Verwijder vraag"):
        if te_verwijderen_vraag != "---":
          huidige_vragen.remove(te_verwijderen_vraag)
          set_setting("vragen", huidige_vragen)
          st.rerun()

      st.write("Huidige lijst:", huidige_vragen)

  elif admin_pass != "":
    st.error("Verkeerd wachtwoord.")
