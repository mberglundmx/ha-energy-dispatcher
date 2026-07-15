# Design Specification: Home Assistant `energy_load` Integration

## 1. Syfte

Skapa en Home Assistant custom integration som fungerar som en **energibeslutsmotor** för styrbara laster.

Integrationens uppgift är att avgöra:

> "Är detta en lämplig tidpunkt att använda energi för denna last, och vilken energikälla är mest lämplig?"

Integrationens output ska användas av vanliga Home Assistant-automationer som sedan styr den fysiska apparaten.

Exempel:

Integration:

```
energy_load.avfuktare

state:
ON

energy_mode:
SOLAR
```

Automation:

```
Om energy_mode = SOLAR:
    sätt avfuktarens börvärde till 50 %

Om energy_mode = GRID_CHEAP:
    sätt börvärde till 65 %
```

Integrationens ansvar slutar vid energibeslutet.

---

# 2. Designprinciper

## Separation av ansvar

### Energy Load Integration ansvarar för:

* elpris
* solel
* nettoimport/export
* effekttopp
* ekonomiska regler
* prioritering mellan energikällor
* tillåtelse att köra

### Automationer ansvarar för:

* apparatens funktion
* börvärden
* effektläge
* driftläge
* fysisk styrning

Exempel:

Integration säger:

```
Kör avfuktare med energikälla SOLAR
```

Automation säger:

```
SOLAR = RH 50 %
GRID_CHEAP = RH 65 %
```

---

# 3. Ny Home Assistant-domän

Ny domän:

```
energy_load
```

Exempel:

```
energy_load.vvb
energy_load.avfuktare
energy_load.elbil
```

En `energy_load` representerar en energiförbrukare som kan optimeras.

---

# 4. Entity State

Varje entity har ett huvudstate:

## ON

Lasten rekommenderas att använda energi.

## OFF

Lasten bör inte använda energi.

## LIMITED

Lasten får använda energi men begränsas av någon regel.

## WAITING

Lasten bör köras senare för att uppfylla ett krav.

---

# 5. Entity Attributes

Exempel:

```yaml
energy_load.avfuktare:

state:
  ON

attributes:

  energy_mode:
    SOLAR

  reason:
    solar_surplus

  reason_text:
    "Solöverskott tillgängligt"

  available_power:
    3200

  required_power:
    1400

  price_state:
    LOW

  grid_state:
    NORMAL

  priority:
    5
```

---

# 6. Energikällor

Integrationens beslut baseras på energikällor.

Möjliga states:

```
SOLAR
GRID_FREE
GRID_CHEAP
GRID_NORMAL
GRID_EXPENSIVE
BLOCKED
```

---

## SOLAR

Används när:

* solöverskott finns
* överskottet räcker för lasten
* försäljning av el inte är mer attraktiv än egen användning

Exempel:

Last:

```
VVB:
2200 W
```

Solöverskott:

```
3500 W
```

Exportpris:

```
5 öre/kWh
```

Regel:

```
Exportpris < 20 öre/kWh
```

Resultat:

```
energy_mode = SOLAR
```

---

# 7. Global konfiguration

Konfigureras via Config Flow.

---

# 7.1 Elpris

Källa:

Nord Pool integration.

Konfiguration:

* elområde
* pris-sensor

Prisnivåer:

## Gratis nätel

Exempel:

```
spotpris <= 2 öre/kWh
```

## Billig nätel

Exempel:

```
spotpris < 30 % av rullande veckomedel
```

## Dyr nätel

Exempel:

```
spotpris > 150 % av rullande veckomedel
```

---

# 7.2 Solel

Användaren anger:

```
solar_production_sensor

house_consumption_sensor
```

Integration räknar:

```
solar_surplus =
produktion - förbrukning
```

Exempel:

```
5000 W produktion
-
2000 W förbrukning

=
3000 W överskott
```

---

# 7.3 Exportpris

Konfigureras separat.

Exempel:

```
selling_price_sensor
```

eller:

```
spotpris + fast ersättning
```

Används för att avgöra om egenanvändning är bättre än försäljning.

---

# 7.4 Effektvakt

Valfri funktion.

Input:

Antingen:

```
grid_power_sensor
```

eller nätbolagsintegration.

Tillstånd:

```
NORMAL
WARNING
CRITICAL
```

Effektvakt har högsta prioritet.

---

# 8. Skapa Energy Load

Via GUI.

## Namn

Exempel:

```
Källaravfuktare
```

## Effektbehov

Exempel:

```
1400 W
```

## Prioritet

1-10

Lägre prioritet stoppas först.

---

# 9. Lastregler

Reglerna beskriver vilka energikällor lasten får använda.

Exempel:

## Avfuktare

```yaml
power:
  required: 1400

priority:
  5

allowed_sources:

  solar:
    enabled: true

    minimum_surplus:
      1400

    max_export_price:
      20


  grid_cheap:
    enabled:
      true


  grid_expensive:
    enabled:
      false


runtime:

  minimum_minutes_per_day:
    180
```

---

# 10. Beslutsmotor

Regler körs i prioriterad ordning.

## Prioritet

```
1. Effektvakt
2. Manuella overrides
3. Lastprioritering
4. SOLAR-värdering
5. GRID_CHEAP
6. GRID_NORMAL
7. Komfortkrav
```

---

# 11. Exempel: Avfuktare

Input:

```
Solöverskott:
2500 W

Avfuktare:
1400 W

Exportpris:
5 öre
```

Resultat:

```
energy_load.avfuktare

state:
ON

energy_mode:
SOLAR
```

Automation:

```
SOLAR:
börvärde 50 %

```

---

Nästa scenario:

```
Solöverskott:
0 W

Elpris:
20 öre

```

Resultat:

```
state:
ON

energy_mode:
GRID_CHEAP
```

Automation:

```
GRID_CHEAP:
börvärde 65 %
```

---

# 12. Services

## Override

```
energy_load.override
```

Exempel:

```yaml
entity_id:
  energy_load.vvb

mode:
  force_on

duration:
  2h
```

---

## Clear override

```
energy_load.clear_override
```

---

## Recalculate

```
energy_load.recalculate
```

---

# 13. Eventlogg

Alla beslut ska loggas.

Exempel:

```
10:32

Avfuktare:

OFF -> ON

Reason:
SOLAR

Solar surplus:
3200 W

Load:
1400 W

Export price:
4 öre
```

---

# 14. Framtida funktioner

## Automatisk lastbalansering

Tillgänglig effekt:

```
4000 W
```

Laster:

```
VVB       2200 W
Avfuktare 1400 W
Elbil     3000 W
```

Prioritet avgör:

```
VVB + Avfuktare körs
Elbil väntar
```

---

## Prognosstyrning

Exempel:

```
Sol väntas om 2 timmar
```

Integration kan skjuta på lågprioritetslaster.

---

## Statistik

Mät:

* ökad egenanvändning av solel
* sparad kostnad
* undvikna effekttoppar
* körtid per energikälla

---

# 15. MVP Implementation

Första version:

1. Custom component
2. Ny domän `energy_load`
3. Config Flow
4. Nord Pool integration
5. Solproduktion + förbrukning
6. Exportpris
7. Effektvakt
8. Decision engine
9. Energy load entity

Exempel automation:

```yaml
trigger:
  state:
    entity_id:
      energy_load.avfuktare

condition:
  state:
    SOLAR

action:
  set humidity:
    50
```

All energilogik ska vara kapslad i integrationen.
