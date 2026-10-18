"""Shared presentation defaults for resort listings."""

RESORT_IMAGES = {
    "sunscape resort": "uploads/resorts/sunscape.png",
    "triple z resort": "uploads/resorts/triple_z.png",
    "magic kingdom resort": "uploads/resorts/magic_kingdom.png",
    "lucky miels resort": "uploads/resorts/lucky_miels.png",
}

RESORT_DESCRIPTIONS = {
    "sunscape resort": "Sunscape Resort is located at South Spring Villas Subdivision, Barangay Bucal, Calamba, Laguna 4027. It offers a spacious, relaxing outdoor area for swimming and group activities, with an adult pool, kiddie pool, three air-conditioned rooms, videoke, billiards, parking, CCTV, and pet-friendly facilities. Guests can also use the refrigerator, water dispenser, gas stove, and basic cooking tools.",
    "triple z resort": "Triple Z Resort is located at 55JF+6WG, Barretto Compound, Barangay Pansol, Calamba, Laguna 4027. It offers a private setting for swimming, recreation, and group stays, with an adult pool, kiddie pool, four air-conditioned rooms, Wi-Fi, videoke, billiards, pet-friendly policies, refrigerator, water dispenser, gas stove, cooking tools, and grill.",
    "magic kingdom resort": "Magic Kingdom Resort is located at Indigo Subdivision, Barangay Bagong Kalsada, Calamba, Laguna 4027. It offers a private setting for swimming, recreation, and group stays, with an adult pool, kiddie pool, four air-conditioned rooms, Wi-Fi, videoke, billiards, pet-friendly access, and safe parking.",
    "lucky miels resort": "Lucky Miels Resort is located at Indigo Subdivision, Barangay Bagong Kalsada, Calamba, Laguna 4027. It offers facilities for swimming, accommodation, recreation, and group activities, including adult and kiddie hot spring pools, air-conditioned rooms, Wi-Fi, videoke, billiards, a dart board, arcade, soccer table, kitchen, shower rooms, CCTV, safe parking, and pet-friendly spaces.",
}

RESORT_GALLERY_EXTRAS = {
    "sunscape resort": ["images/pdf_resorts/resort_3_2.png"],
    "triple z resort": ["images/pdf_resorts/resort_6_2.png"],
    "magic kingdom resort": ["images/pdf_resorts/resort_8_2.png"],
    "lucky miels resort": ["images/pdf_resorts/resort_11_2.png"],
}


def enrich_resort(resort):
    """Return a resort with saved values preferred over known presentation defaults."""
    row = dict(resort)
    key = (row.get("resort_name") or "").strip().lower()
    row["logo"] = row.get("logo") or (
        "/static/" + RESORT_IMAGES[key] if key in RESORT_IMAGES
        else "/static/images/default-resort.svg"
    )
    row["description"] = row.get("description") or RESORT_DESCRIPTIONS.get(key)
    return row


def enrich_resorts(resorts):
    return [enrich_resort(resort) for resort in resorts]


def gallery_photos(resort, saved_photos):
    """Build gallery URLs from the resort's main image, saved uploads, and bundled extras."""
    key = (resort.get("resort_name") or "").strip().lower()
    urls = []
    main_image = resort.get("logo")
    if main_image and not main_image.endswith("/default-resort.svg"):
        urls.append(main_image if main_image.startswith("/") else "/static/" + main_image)
    for photo in saved_photos:
        url = photo.get("url") or "/static/" + photo["photo_path"]
        if url not in urls:
            urls.append(url)
    if not saved_photos:
        urls.extend("/static/" + path for path in RESORT_GALLERY_EXTRAS.get(key, []))
    return urls
