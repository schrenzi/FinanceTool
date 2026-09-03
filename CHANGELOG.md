# Changelog

## v0.4.0

- **Auto-Kredit alle Konten**: Sparkonto (+Sparrate) und Anlegekonto (+ETF-Rate + Rendite) werden am Monatsersten automatisch gutgeschrieben
- **Nicht-aliquote Zyklen**: Quartals- und Jahresausgaben/-einnahmen erscheinen nur in ihren Fälligkeitsmonaten statt aliquot verteilt
- **Fälligkeitsmonat**: Neues "Fällig im"-Feld bei Einnahmen und Ausgaben für nicht-monatliche Posten
- **Sonderbuchungen (Boosts)**: Einmalige geplante Einnahmen/Ausgaben zu bestimmten Zeitpunkten (z.B. Weihnachtsgeld, Nachzahlung)
- **Prognose**: Neue "Boost"-Spalte zeigt geplante Sonderbuchungen pro Monat
- **Prognose**: Einnahmen/Ausgaben-Balken variieren je nach Monat (non-aliquot)
- **Datenmodell**: `PlannedBoost`-Modell, `due_month`-Feld auf Expense/Income

## v0.3.0

- **Nutzkonto**: Automatische monatliche Gutschrift am Monatsersten (free_cash - Vormonats-Tagebuch)
- **Nutzkonto**: Tagebuch-Einträge reduzieren den angezeigten Kontostand in Echtzeit
- **Datenmodell**: Neues Feld `last_credited_month` für Buchungstracking
- **Logik**: `before_request`-Hook prüft bei jedem Zugriff ob Monatswechsel stattgefunden hat

## v0.2.0

- **Prognose**: Kuchendiagramm zeigt jetzt variable Ausgaben (Tagebuch) als eigenes orange Segment
- **Prognose**: Tabelle enthält neue Spalte "Var. Ausg." mit dem rollierenden 3-Monats-Mittel
- **Prognose**: Nutzkonto-Prognose berücksichtigt variable Ausgaben (free_cash - var_expenses pro Monat)
- **Dashboard**: Nutzkonto-Stand wird um laufende Tagebuch-Ausgaben reduziert
- **Dashboard**: "Frei verfügbar diesen Monat" zeigt Restbudget nach Tagebuch-Abzug
- **Tagebuch**: Neue Kategorien Arzt/Gesundheit und Friseur/Körperpflege
- **3-Monats-Mittel**: Default 600 € für Monate ohne Daten, danach echte Werte

## v0.1.0

- **Dashboard**: Finanzübersicht mit Einnahmen, Fixkosten, Sparrate, ETF, frei verfügbar
- **Dashboard**: Kontostand-Kacheln (Nutzkonto, Sparkonto, Anlegekonto)
- **Einnahmen/Ausgaben**: CRUD für Einnahmen und Ausgaben nach Kostenstellen
- **Tagebuch**: Tägliche variable Ausgaben tracken (Restaurant, Bar, Kino, Events, etc.)
- **Konten**: Kontostände und Sparraten konfigurieren
- **Prognose**: 12-Monats-Prognose mit Charts und Tabelle
- **Mobile**: PWA-ready, optimiert für iPhone-Nutzung
- **Deployment**: Render-Konfiguration mit PostgreSQL-Support
