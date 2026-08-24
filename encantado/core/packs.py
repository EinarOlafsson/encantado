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
           "Huge community library. Licences vary per file — CC0 needs nothing, "
           "CC-BY needs credit, and some are non-commercial. Check each one.",
           "https://freesound.org/search/?q={q}"),
    Vendor("labs", "Spitfire LABS", "https://labs.spitfireaudio.com", "free",
           "Free, properly licensed for commercial use, and genuinely good. "
           "Strings, soft pianos, choir, textures — the breakdown palette."),
    Vendor("pianobook", "Pianobook", "https://www.pianobook.co.uk", "free",
           "Community-made sampled instruments, free. Characterful pianos, "
           "found-sound textures and oddities."),
    Vendor("99sounds", "99Sounds", "https://99sounds.org", "free",
           "Curated free packs: drum machines, percussion, cinematic hits."),
    Vendor("cymatics", "Cymatics", "https://cymatics.fm", "free",
           "Regularly gives away large packs aimed at electronic producers. "
           "Email signup required."),
    Vendor("komplete_start", "Komplete Start", "https://www.native-instruments.com",
           "free",
           "Native Instruments' free bundle — synths, sampled instruments and "
           "loops. Search their site for Komplete Start."),
    Vendor("musicradar", "MusicRadar SampleRadar",
           "https://www.musicradar.com", "free",
           "A long-running archive of free, royalty-free packs including house "
           "and techno kits. Search the site for SampleRadar."),
    Vendor("bbc", "BBC Sound Effects", "https://sound-effects.bbcrewind.co.uk",
           "free",
           "Thousands of field recordings. The RemArc licence covers personal, "
           "educational and research use — read it before commercial release."),
    Vendor("looperman", "Looperman", "https://www.looperman.com", "free",
           "Free loops uploaded by users. Quality varies and most require "
           "crediting the uploader — check each entry's terms."),

    # --- free instruments: for this music these matter more than samples ---
    Vendor("vital", "Vital (free synth)", "https://vital.audio", "synth",
           "Free wavetable synth in the same class as Serum. This is the single "
           "most useful free download for supersaws, plucks and growling basses.",
           ),
    Vendor("surge", "Surge XT (free synth)",
           "https://surge-synthesizer.github.io", "synth",
           "Free and open source, and very deep. Good at plucks, pads and "
           "everything in between."),
    Vendor("dexed", "Dexed (free FM synth)", "https://asb2m10.github.io/dexed/",
           "synth",
           "Free DX7 emulation. The classic FM electric pianos and bells that "
           "sit under piano-house breakdowns."),
    Vendor("tal", "TAL-NoiseMaker (free synth)",
           "https://tal-software.com", "synth",
           "Free subtractive synth. Fast for plucks, stabs and analogue basses."),
    Vendor("decent", "Decent Sampler (free)", "https://www.decentsamples.com",
           "free",
           "Free sampler player with a large catalogue of free libraries, "
           "including many from Pianobook."),
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


FREE_PICKS: tuple[PackGuide, ...] = (
    PackGuide("free-synths", "Free synths (start here)", "Free",
              "For this genre the leads, plucks, pads and basses are "
              "synthesised, not sampled — so a free synth gets you closer than "
              "any free sample pack. Vital is the one to download first.",
              ("vital wavetable synth", "surge xt", "dexed dx7"),
              ("vital", "surge", "dexed", "tal"), "supersaw / pluck / bass"),
    PackGuide("free-breakdown", "Free strings, pianos and choir", "Free",
              "Spitfire LABS is free, licensed for commercial use and genuinely "
              "high quality — the fastest way to a convincing breakdown.",
              ("labs strings", "labs soft piano", "labs choir"),
              ("labs", "pianobook", "decent"), "pad / chords"),
    PackGuide("free-perc", "Free organic percussion", "Free",
              "Congas, shakers, rims, wood and found sounds — the layer that "
              "makes the French melodic-house records breathe.",
              ("conga", "shaker", "percussion loop", "hand percussion"),
              ("freesound", "musicradar", "99sounds"), "perc"),
    PackGuide("free-drums", "Free drum machines and kits", "Free",
              "808/909-lineage one-shots and house kits. Encantado synthesises "
              "its own, but real one-shots layer well underneath them.",
              ("drum machine samples", "house drum kit", "analog drums"),
              ("99sounds", "musicradar", "komplete_start"), "kick / clap / hat"),
    PackGuide("free-texture", "Free textures and field recordings", "Free",
              "Atmospheres, room tone and noise beds. A quiet field recording "
              "under a breakdown does more than another synth layer.",
              ("field recording", "atmosphere", "room tone", "rain"),
              ("freesound", "bbc", "labs"), "sampler"),
    PackGuide("free-vocal", "Free vocal material", "Free",
              "The category where licensing matters most. Prefer CC0, and read "
              "the terms before you release anything commercially.",
              ("vocal chop", "acapella cc0", "vocal phrase"),
              ("freesound", "looperman", "cymatics"), "sampler"),
)


def all_guides() -> tuple[PackGuide, ...]:
    return FREE_PICKS + PACK_GUIDES


def guide(key: str) -> PackGuide | None:
    for g in all_guides():
        if g.key == key:
            return g
    return None


CATEGORIES = ("Free", "Drums", "Bass", "Melodic", "Vocals", "FX", "Presets")

DISCLAIMER = (
    "Encantado bundles no third-party audio. These are pointers to the rights "
    "holders' own stores. No public, verified list exists of the exact packs any "
    "of these artists used, so nothing here claims to be one — the artist "
    "searches simply query each store directly, which is where an official pack "
    "would appear if one exists."
)
