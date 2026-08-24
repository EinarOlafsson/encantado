"""Where to legitimately buy the sounds this genre is built from.

An important caveat, stated plainly here and in the UI: no producer publishes a
verified list of the exact sample packs they used, and Encantado does not
pretend to know one. What this catalogue gives you is the set of *legitimate
storefronts* the melodic-house and progressive scene actually buys from, plus
ready-made search terms — including per-artist searches, so any official pack an
artist has released surfaces at the source rather than being guessed at here.

Nothing here is affiliated with Encantado, and no audio is bundled or
redistributed. Every entry is a pointer to the rights holder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Vendor:
    key: str
    name: str
    url: str
    kind: str                      # 'samples' | 'synth' | 'free'
    note: str
    search_url: str = ""           # only where the pattern is known to be stable

    def search(self, term: str) -> str:
        if self.search_url:
            return self.search_url.format(q=quote_plus(term))
        return self.url


VENDORS: tuple[Vendor, ...] = (
    Vendor("splice", "Splice", "https://splice.com/sounds", "samples",
           "Subscription sample marketplace. The widest catalogue for house and "
           "progressive, and where most official artist packs end up.",
           "https://splice.com/sounds/search?q={q}"),
    Vendor("loopmasters", "Loopmasters", "https://www.loopmasters.com", "samples",
           "Pay-per-pack sample house with a deep melodic and deep-house "
           "catalogue. Buy once, keep the files."),
    Vendor("adsr", "ADSR Sounds", "https://www.adsrsounds.com", "samples",
           "Sample packs and preset banks, frequently discounted. Good source "
           "for Serum and Sylenth1 preset collections."),
    Vendor("beatport", "Beatport Sounds", "https://sounds.beatport.com", "samples",
           "Beatport's own sample store, strong on club-oriented material."),
    Vendor("ni", "Native Instruments", "https://www.native-instruments.com",
           "samples", "Komplete and the Play series. Expansions such as the "
           "house and melodic-techno packs are curated for exactly this genre."),
    Vendor("output", "Output", "https://output.com", "samples",
           "Arcade and the cinematic instruments. Useful for the textural, "
           "film-score side of melodic house."),
    Vendor("spitfire", "Spitfire Audio", "https://www.spitfireaudio.com", "samples",
           "Orchestral and textural libraries. LABS is free and is a genuinely "
           "good source of strings and piano for breakdowns."),
    Vendor("xfer", "Xfer Records — Serum", "https://xferrecords.com", "synth",
           "Serum is the default modern soft synth for this music. Most "
           "commercial preset banks for the genre target it."),
    Vendor("lennar", "LennarDigital — Sylenth1", "https://www.lennardigital.com",
           "synth",
           "Widely associated with the 2010–2013 progressive and big-room sound. "
           "Still excellent for supersaw leads and plucks."),
    Vendor("refx", "reFX — Nexus", "https://refx.com", "synth",
           "A preset-based rompler heavily associated with that same era of "
           "festival progressive house."),
    Vendor("reveal", "Reveal Sound — Spire", "https://www.reveal-sound.com", "synth",
           "Favoured for trance and progressive leads and plucks."),
    Vendor("uhe", "u-he — Diva / Repro / Hive", "https://u-he.com", "synth",
           "Analogue-modelled synths. Diva in particular suits the warmer, "
           "French melodic-house and synthwave palette."),
    Vendor("arturia", "Arturia V Collection", "https://www.arturia.com", "synth",
           "Emulations of the classic analogue hardware behind a lot of the "
           "French-touch lineage."),
    Vendor("freesound", "Freesound", "https://freesound.org", "free",
           "Community library, largely Creative Commons. Check each file's "
           "licence — some require attribution.",
           "https://freesound.org/search/?q={q}"),
    Vendor("labs", "Spitfire LABS", "https://labs.spitfireaudio.com", "free",
           "Free, high quality, and licensed for commercial use. Strings, "
           "pianos, choirs and textures."),
    Vendor("cymatics", "Cymatics", "https://cymatics.fm/pages/free-download-vault",
           "free", "Regularly gives away large free sample packs aimed at "
           "electronic producers."),
)


def vendor(key: str) -> Vendor | None:
    for v in VENDORS:
        if v.key == key:
            return v
    return None


# --------------------------------------------------------------------------
# Artists — search links, so official packs surface from the source
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Artist:
    name: str
    note: str
    vendors: tuple[str, ...] = ("splice", "loopmasters", "adsr")


ARTISTS: tuple[Artist, ...] = (
    Artist("Swedish House Mafia",
           "Festival progressive. Supersaw stacks, huge piano breakdowns."),
    Artist("Avicii",
           "Piano house and folk-tinged progressive. Bright plucks and pianos."),
    Artist("Warakls",
           "French melodic house on Hungry Music. Cinematic arps, organic percussion."),
    Artist("NTO",
           "French melodic techno and house. Deep sub, filtered stabs, long builds."),
    Artist("Joachim Pastor",
           "Melodic house on Hungry Music. Rolling plucks and warm analogue bass."),
    Artist("Joris Delacroix",
           "French melodic and deep house. Textural pads, restrained grooves."),
    Artist("French 79",
           "Marseille synthwave. Analogue arps, gated strings, slower tempos."),
    Artist("MEDUZA",
           "Modern melodic and tech house. Vocal chops, tight plucky basslines."),
    Artist("Robin Schulz",
           "Tropical and deep house. Marimba plucks, soft kicks, airy pads."),
)


# --------------------------------------------------------------------------
# What to actually look for, per role in a track
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class PackGuide:
    key: str
    title: str
    category: str
    blurb: str
    search_terms: tuple[str, ...]
    vendors: tuple[str, ...]
    channel_hint: str = ""          # which Encantado instrument it replaces/layers


PACK_GUIDES: tuple[PackGuide, ...] = (
    PackGuide("drums-melodic", "Melodic House Drums", "Drums",
              "Rounded kicks, soft claps, live-feel percussion loops. The "
              "organic percussion layer is what separates this genre from "
              "big-room.",
              ("melodic house drums", "organic house percussion",
               "deep house drum kit"),
              ("splice", "loopmasters", "beatport"), "kick / clap / perc"),
    PackGuide("drums-progressive", "Progressive & Festival Drums", "Drums",
              "Long-decay kicks with strong click, wide layered claps, "
              "crashes and impacts for drops.",
              ("progressive house drums", "festival drums", "big room kick"),
              ("splice", "adsr", "beatport"), "kick / clap / cymbal"),
    PackGuide("perc-organic", "Organic & World Percussion", "Drums",
              "Congas, shakers, rims, wood and found-sound hits — the layer "
              "that makes NTO and Warakls records breathe.",
              ("organic percussion", "world percussion loops",
               "afro house percussion"),
              ("splice", "loopmasters", "freesound"), "perc"),
    PackGuide("bass-house", "House Bass & Sub", "Bass",
              "Sub one-shots and bass loops. Useful as reference even if you "
              "synthesise your own.",
              ("deep house bass", "melodic house bassline", "sub bass one shot"),
              ("splice", "loopmasters"), "bass"),
    PackGuide("plucks", "Plucks & Arps", "Melodic",
              "The signature melodic-house lead texture. Preset banks often "
              "beat sample packs here — a pluck you can retune is worth more "
              "than one you cannot.",
              ("melodic house plucks", "arp loops", "analog pluck"),
              ("splice", "adsr", "xfer"), "pluck"),
    PackGuide("keys", "Pianos, Keys & Organs", "Melodic",
              "Acoustic and electric pianos for breakdowns and piano-house "
              "riffs. Spitfire LABS is free and genuinely good here.",
              ("house piano", "electric piano", "piano house loops"),
              ("labs", "ni", "spitfire"), "fm / organ"),
    PackGuide("pads", "Pads, Strings & Textures", "Melodic",
              "Evolving pads and string beds for breakdowns and intros.",
              ("cinematic pads", "ambient textures", "string pads"),
              ("labs", "output", "spitfire"), "pad / choir"),
    PackGuide("vocals", "Vocal Chops & Phrases", "Vocals",
              "Royalty-free vocal chops and top lines. Check the licence — "
              "vocals are the one category where clearance matters most.",
              ("vocal chops house", "melodic house vocals", "acapella royalty free"),
              ("splice", "loopmasters"), "sampler"),
    PackGuide("fx", "Risers, Impacts & FX", "FX",
              "Uplifters, downlifters, impacts and noise sweeps for transitions.",
              ("risers and impacts", "transition fx", "uplifter"),
              ("splice", "cymatics", "adsr"), "sweep"),
    PackGuide("presets-serum", "Serum Preset Banks", "Presets",
              "For the genre's leads, plucks and basses. A preset you can "
              "reshape beats a rendered sample every time.",
              ("serum melodic house presets", "serum progressive presets"),
              ("adsr", "splice", "xfer"), "—"),
    PackGuide("presets-sylenth", "Sylenth1 & Spire Banks", "Presets",
              "The classic progressive supersaw and pluck sound.",
              ("sylenth1 progressive house", "spire trance presets"),
              ("adsr", "lennar", "reveal"), "—"),
    PackGuide("free", "Free & Creative Commons", "Free",
              "Legitimately free material to start with. Freesound licences "
              "vary per file — read them; some need attribution.",
              ("house drums", "percussion", "field recording"),
              ("labs", "freesound", "cymatics"), "any"),
)


def guide(key: str) -> PackGuide | None:
    for g in PACK_GUIDES:
        if g.key == key:
            return g
    return None


CATEGORIES = ("Drums", "Bass", "Melodic", "Vocals", "FX", "Presets", "Free")

DISCLAIMER = (
    "Encantado bundles no third-party audio. These are pointers to the rights "
    "holders' own stores. No public, verified list exists of the exact packs any "
    "of these artists used, so nothing here claims to be one — the artist "
    "searches simply query each store directly, which is where an official pack "
    "would appear if one exists."
)
