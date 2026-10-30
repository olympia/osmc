# Vero V poszterszél-diagnosztika

Ez a diagnosztikai patch a Kodi CPU oldali képadatát hasonlítja össze a
GPU-n megjelenő eredménnyel. Nem javítja és nem változtatja meg a skálázást,
a képpontokat, a keretet vagy a szűrési beállításokat.

## Forrás és buildbe illesztés

- Cél: `vero5`, Kodi 21.3, `a3a448d26b8d560a65655dab2cd122994dc4e146`.
- Patch: `package/mediacenter-osmc/patches/vero5-919-olympia-texture-edge-diagnostics.patch`.
- A meglévő `all-*`, `arm-*`, `vero5-*` sor végére kerül; a 912-es edge-clamp
  javítás megmarad. A `build.sh` és a csomagverzió nincs módosítva.
- A szokásos `make vero5` később automatikusan felveszi. Ez a dokumentum nem
  jelent build- vagy telepítési jóváhagyást. A készítés során ezek nem történtek meg.
- A Windows alatti külön tesztmappa a teljes patchsor alkalmazhatóságát vizsgálja,
  nem ARM-fordítás vagy készülékes működési teszt.

## Mit mér?

Egy kiválasztott helyi JPEG/PNG cache-fájl minden új betöltése azonosítót kap.
A Kodi ugyanazt a betöltött textúrát többször is megrajzolhatja; ilyenkor az ID
változatlan, és nem készül új CPU-mentés.

| Fázis | Jelentés |
|---|---|
| `decoded` | Dekódolás/átméretezés után, a `ClampToEdge()` előtt |
| `clamped` | A szélek kitöltése után |
| `upload` | A GLES-nek átadott teljes puffer, az esetleges BGRA/RGBA csere után |

A `.raw` fájlok a teljes foglalást, így a jobb és alsó kitöltést is tartalmazzák.
A `.meta` fájlok rögzítik a valódi képméretet, textúraméretet, sorhosszt,
színcsatornasorrendet, alfa/orientáció adatot és a kitöltés eltéréseit.
Ez a mérés normál, 32 bites poszterekre készült, nem DDS/XBT/animált képekre.

Az `events.tsv` időbélyegei Unix epoch ezredmásodpercek. Az `upload` rekord
a GL-textúra nevét, a feltöltési formátumot, sorigazítást, a ténylegesen lekérdezett
min/mag szűrést, wrap-paramétereket és a mipmap-kérést tartalmazza. Ez bemeneti
állapot, nem a GPU-feltöltés sikerének igazolása. A meglévő Kodi GL-hibaellenőrzés
megmarad; a `kodi.log` is kell a vizsgálathoz.

A `draw` rekord a textúra ID-jához tartozó csúcspontokat és UV-koordinátákat
mutatja, legfeljebb 36 csúcspontig, textúra-ID és megjelenítő objektum páronként
legfeljebb 250 ms-onként. A `control` mező a GUITexture objektum folyamaton belüli
címe; élettartama alatt azonosítja a megjelenítési helyet, újraindítások között nem.
Így egy poszter és a vele közös textúrát használó tükröződés nem nyomja el egymás
mintáit. Legfeljebb 128 ilyen pár követhető; ezen túl `draw_tracker_limit_reached`
jelzi az új kontrollok kihagyását. Az események száma összesen 2000, utána egy
`event_limit_reached` rekord jelzi a napló végét; nem minden képkocka kerül naplóba.
Érdemes a jó/hibás állapotot néhány másodpercig képernyőn hagyni.

## Egy célkép kiválasztása

Ne töröld a thumbnail cache-t. Egy olyan posztert válassz, amely gyakran mutatja
a hibát, és keresd meg a hozzá tartozó `.jpg`/`.png` fájlt a Vero
`/home/osmc/.kodi/userdata/Thumbnails` mappájában. Több profil vagy áthelyezett
adatkönyvtár esetén a tényleges útvonalat használd.

Segítségként az alábbi olvasási lekérdezés a legutóbb használt cache-bejegyzéseket
listázza, ha van Python 3 a készüléken. Az URL nem feltétlenül tartalmaz filmcímet;
a kiválasztott képet PC-n megnyitva is ellenőrizd.

```bash
python3 - <<'PY'
import sqlite3
from pathlib import Path
p = Path('/home/osmc/.kodi/userdata/Database/Textures13.db')
db = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True)
for row in db.execute('''SELECT t.cachedurl, s.width, s.height, t.url
                         FROM texture t JOIN sizes s ON s.idtexture=t.id
                         WHERE s.size=1 ORDER BY s.lastusetime DESC LIMIT 40'''):
    print(row)
db.close()
PY
```

A `cachedurl`, például `a/abcdef01.jpg`, a `Thumbnails` könyvtárhoz képest relatív.
A példabeli fájlnév helyett minden alábbi parancsban a tényleges nevet használd.

## Aktiválás – csak a később jóváhagyott build és telepítés után

A következő parancsok a Vero eszközön futtatandók, az `osmc` felhasználóként.
Az újraindítás megszakítja a lejátszást; teszteléskor, leállított lejátszás mellett használd.

```bash
target='/home/osmc/.kodi/userdata/Thumbnails/a/abcdef01.jpg'
test -f "$target" && printf '%s\n' "$target" > /home/osmc/.kodi/temp/texture-edge-diagnostics.conf
sha256sum "$target"
sudo systemctl restart mediacenter
```

A config első sora **egyetlen teljes, helyi fájlútvonal**, idézőjelek nélkül.
Nincs glob, URL, mappaszűrő vagy „minden kép” mód. A Kodi a `special://` útvonalakat
feloldja, de nem végez symlink-/kisbetűs normalizálást. A configot folyamatonként
egyszer olvassa: módosításhoz újraindítás szükséges.

A `kodi.log` induláskor `TextureEdgeDiag v1: enabled; output ...` sort ír.
A `special://temp/texture-edge-diag-XXXXXX` friss mappában lesznek a mentések.
A `source.txt` tartalmazza a célútvonalat. Config nélkül nem keletkezik diagnosztikai
mappa vagy napló. Érvényes configgal a mappa akkor is létrejön, ha a célképet még nem
töltöttük be; a tényleges egyezést a `begin` és `dump` események igazolják.

Egy folyamat legfeljebb 20 egyező betöltést és 128 MiB nyers adatot ment,
plusz kis metaadat-/eseményfájlokat. Ha nem fér el egy teljes mentés, kimarad és
`dump_skipped` rekord keletkezik. Nincs automatikus takarítás; újraindításonként új
mappa keletkezik. A régi mérési mappákat archiválás után kézzel lehet eltávolítani.

## Jó és hibás állapot rögzítése

1. Nyisd meg a célposztert. Böngéssz úgy, ahogy rendesen előjön a hiba.
2. Jó és hibás állapotban készíts **Kodi saját képernyőmentést**. Jegyezd fel az
   állapotot és időpontot, majd hagyd néhány másodpercig képernyőn a posztert.
   A Vero órája az irányadó; SSH-n a `date -u '+%Y-%m-%dT%H:%M:%S.%3NZ'`
   megmutatja az aktuális UTC-időt. A fájl másolási időpontja nem azonos a felvételével.
3. Az időponthoz tartozó `draw` rekord ID-ját használd. Ne csak a legutolsó `begin`
   sorból következtess: a betöltés háttérben is megtörténhet. Több nézetnél a
   képernyőkoordinátákat is ellenőrizd. Jó és hibás állapothoz ugyanaz az ID is tartozhat.
4. Ismét futtasd a `sha256sum "$target"` parancsot. A cache-fájl ne változzon a
   két megfigyelés között. Másold át a célképet, a teljes mérési mappát,
   képernyőmentéseket, az időpont-/ID-jegyzetet és a `kodi.log` fájlt a PC-re.
5. Ha nincs egyező betöltés, ellenőrizd a célútvonalat és a profilt. A GPU-n már
   bent levő textúra nem töltődik újra pusztán a config létrehozásától; kell az újraindítás.

A mentés és a naplózás rövid megakadást okozhat, módosíthatja az időzítést.
Ha emiatt eltűnik a hiba, a mérés **nem zárja ki** az eredeti problémát.

## Kiértékelés PC-n

Az `analyze.py` Python 3.8+-t használ, külső csomag nélkül. A forrásmappát nem
módosítja; az `--out` új, még nem létező kimeneti mappa legyen.

```text
python analyze.py "C:\meres\texture-edge-diag-ABC123" --out "C:\meres\eredmeny" --good 2 --bad 5
```

Az ID-k opcionálisak, de csak együtt adhatók meg. Ugyanaz az ID is megadható
mindkettőre, ha a képernyő állapota új feltöltés nélkül változott.

Kimenetek:

- `report.md`, `report.json`: méretek, hash-ek, kitöltési hibák és fázisonkénti összevetés.
- `*-image.png`: csak a valódi kép, alfával.
- `*-texture.png`: teljes textúra, a kitöltéssel együtt.
- `*-edge.png`: az utolsó 8 képoszlop és legfeljebb 8 kitöltési oszlop négyszeres nagyításban.
- `*-alpha.png`: az alfaértékek önálló, átlátszatlan szürkeárnyalatos képe.

A PNG-k nem alkalmaznak orientációs forgatást. A segéd a BGRA/RGBA sorrendet
egységesíti, így a megengedett csatornacsere nem lesz téves eltérés. Az eredeti nyers
fájlokat és külön hash-üket is megőrizzük. Hibás/csonka/hiányos mentés figyelmeztetést
és 1-es kilépési kódot ad; argumentum-/kimeneti hiba 2-est.

## Az eredmények értelmezése

| Megfigyelés | Következtetés / következő vizsgálat |
|---|---|
| Csak a `decoded` kitöltése változik | Önmagában normális: a kitöltés itt még nincs inicializálva |
| `clamped` vagy `upload` jobb/alsó kitöltése hibás | CPU oldali kitöltési vagy későbbi puffermódosítás vizsgálandó |
| Azonos cache-fájl és méret mellett a valódi képpontok változnak betöltésenként | CPU oldali dekódolás/átméretezés/memóriakezelés gyanús |
| `decoded` és `clamped` valódi képpontjai eltérnek | A kitöltés a képtartományt is érinti, vagy közben más módosítja a puffert |
| `clamped` és normalizált `upload` valódi képpontjai eltérnek | A két mérési pont közötti útvonal vizsgálandó |
| Feltöltés előtti kép és kitöltés hibátlan, a hozzá tartozó Kodi-mentés hibás | Feltöltés, koordináták, rajzolás, keret/diffuse réteg vagy driver felé kell továbbmenni |
| Ugyanaz a GPU-textúra/ID egyszer jó, máskor hibás | A CPU-mentések önmagukban nem magyarázzák; a rajzolási állapotot és a GPU-oldalt kell tovább vizsgálni |

Az egyező hash **nem bizonyít vizuális hibátlanságot**: ugyanaz a rossz kép is
egyezhet. A képeket a forrással és képernyőmentésekkel is ellenőrizni kell.
Ez a patch nem olvassa vissza a GPU textúráját; nem különíti el önmagában a
driverhibát a Kodi feltöltési/rajzolási hibájától. Hiányzó upload-mentés esetén
nem szabad végleges CPU/GPU következtetést levonni.

## Kikapcsolás

A teszt végén nevezd át a `texture-edge-diagnostics.conf` fájlt például
`texture-edge-diagnostics.conf.disabled` névre, majd indítsd újra a Kodit.
Az átnevezéshez ne írj felül meglévő fájlt. A korábbi mérési mappák megmaradnak.

## Helyi ellenőrzés

```text
python -B tools/texture-edge-diagnostics/test_analyze.py
```

A mesterséges tesztek ellenőrzik a BGRA/RGBA-egyezést, az alfaadatot, a régi
első-soros clamp-hibához hasonló kitöltést, a csonka mentést, a hibás geometriát,
a hiányzó fázist, az eltérő képadatot és a generált PNG bájtjait/CRC-it.
Nem helyettesítik a későbbi Vero V fordítást és készülékes próbát.
