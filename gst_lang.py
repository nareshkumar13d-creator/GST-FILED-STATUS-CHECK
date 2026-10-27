"""Bhasha (Hinglish / English / Hindi): poori app, report aur WhatsApp message ke liye ek hi jagah.

T("Hinglish text")  -> app ke label / button / message ka chuni hui bhasha me text
L(text, lang)       -> dynamic text (status, error, mahine ke naam) ko chuni hui bhasha me badalta hai
"""
import re

LANGS = {"Hinglish": "hl", "English": "en", "हिंदी": "hi"}
CODE = "hl"


def set_lang(code):
    global CODE
    CODE = code if code in ("hl", "en", "hi") else "hl"


def load_choice():
    import gst_settings
    set_lang(gst_settings.load().get("lang", "hl"))


def save_choice():
    import gst_settings
    gst_settings.update(lang=CODE)


def lang_name():
    return next(k for k, v in LANGS.items() if v == CODE)


# ---------------------------------------------------------------- mahine, shabd
MONTHS_HI = {"Jan": "जनवरी", "Feb": "फरवरी", "Mar": "मार्च", "Apr": "अप्रैल", "May": "मई", "Jun": "जून",
             "Jul": "जुलाई", "Aug": "अगस्त", "Sep": "सितंबर", "Oct": "अक्टूबर", "Nov": "नवंबर", "Dec": "दिसंबर"}
MONTH_RE = re.compile(r"\b(" + "|".join(MONTHS_HI) + r")\b")

# Report ke fixed header / label (exact match)
EXACT = {
    "en": {"Mahine-wise": "Month-wise", "Report ki date": "Report date", "Rang": "Colour", "Matlab": "Meaning",
           "Hara": "Green", "Peela": "Yellow", "Laal": "Red", "Bhoora": "Grey",
           "Filed (time par)": "Filed (on time)", "Filed, par late": "Filed, but late",
           "Abhi due nahi / is mahine ka return nahi banta (quarterly)": "Not yet due / no return this month (quarterly)",
           "Saal (FY)": "Year (FY)", "Due date badli hui": "Changed due dates", "Koi nahi": "None"},
    "hi": {"S.No": "क्र.सं.", "GSTIN": "GSTIN", "Party name": "पार्टी का नाम", "Mobile": "मोबाइल",
           "Frequency": "रिटर्न का प्रकार", "GST type / status": "जीएसटी प्रकार / स्थिति",
           "GSTR-1 latest": "GSTR-1 ताज़ा", "GSTR-1 status": "GSTR-1 स्थिति",
           "GSTR-3B latest": "GSTR-3B ताज़ा", "GSTR-3B status": "GSTR-3B स्थिति",
           "Composition: CMP-08 / GSTR-4": "कम्पोज़िशन: CMP-08 / GSTR-4", "Note": "टिप्पणी",
           "Legal name": "क़ानूनी नाम", "Trade name": "व्यापारिक नाम", "Taxpayer type": "करदाता प्रकार",
           "GST status": "जीएसटी स्थिति", "Cancel date": "रद्द होने की तारीख", "Registration date": "पंजीकरण तिथि",
           "Constitution": "संगठन का प्रकार", "Address": "पता", "State jurisdiction": "राज्य क्षेत्राधिकार",
           "Centre jurisdiction": "केंद्र क्षेत्राधिकार", "Summary": "सारांश", "Mahine-wise": "महीनेवार",
           "Party details": "पार्टी विवरण", "Info": "जानकारी", "GST return status report": "जीएसटी रिटर्न स्थिति रिपोर्ट",
           "Report ki date": "रिपोर्ट की तारीख", "Rang": "रंग", "Matlab": "मतलब", "Hara": "हरा", "Peela": "पीला",
           "Laal": "लाल", "Bhoora": "धूसर", "Filed (time par)": "समय पर फाइल हुआ", "Filed, par late": "फाइल हुआ, पर देरी से",
           "Abhi due nahi / is mahine ka return nahi banta (quarterly)": "अभी देय नहीं / इस महीने का रिटर्न नहीं बनता (त्रैमासिक)",
           "Saal (FY)": "वर्ष (FY)", "Return type": "रिटर्न प्रकार", "Due date badli hui": "बदली हुई देय तारीखें",
           "Koi nahi": "कोई नहीं"},
}

# Dynamic text (status / error / note) ke phrase; lambe phrase pehle
PHRASES = {
    "en": [("Is saal me portal ne koi return record nahi diya", "Portal returned no return record for this year"),
           ("is mahine ka return nahi banta (quarterly)", "no return this month (quarterly)"),
           ("GSTIN galat hai (format/checksum)", "Invalid GSTIN (format/checksum)"),
           ("Captcha galat ya expire ho gaya.", "Captcha was wrong or expired."),
           ("Portal ne GSTIN accept nahi kiya", "Portal did not accept the GSTIN"),
           ("Portal ne request rok di (HTTP", "Portal blocked the request (HTTP"),
           (". Thodi der baad try karo.", ". Try again after a while."),
           ("Portal ka jawab samajh nahi aaya (JSON nahi mila).", "Could not understand the portal's reply (no JSON found)."),
           ("Return table nahi mila (portal ka format badla ho sakta hai). 'Raw response' dekho.",
            "Return table not found (the portal format may have changed). See 'Raw response'."),
           ("Portal se ", "From portal: "), (" record mile par padh nahi paaye. Pehla record: ",
                                             " records found but could not be read. First record: "),
           ("(list khali)", "(empty list)"),
           ("din late", "days late"), ("koi filing nahi", "no filing found"), ("Abhi due nahi", "Not yet due"),
           ("Portal par nahi mila", "Not found on portal"), ("Skip kiya", "Skipped")],
    "hi": [("Is saal me portal ne koi return record nahi diya", "इस वर्ष पोर्टल ने कोई रिटर्न रिकॉर्ड नहीं दिया"),
           ("GSTIN galat hai (format/checksum)", "GSTIN गलत है (फॉर्मैट/चेकसम)"),
           ("Captcha galat ya expire ho gaya.", "कैप्चा गलत था या समाप्त हो गया।"),
           ("Portal ne GSTIN accept nahi kiya", "पोर्टल ने GSTIN स्वीकार नहीं किया"),
           ("Portal ne request rok di (HTTP", "पोर्टल ने अनुरोध रोक दिया (HTTP"),
           (". Thodi der baad try karo.", "। थोड़ी देर बाद फिर कोशिश करें।"),
           ("Portal ka jawab samajh nahi aaya (JSON nahi mila).", "पोर्टल का जवाब समझ नहीं आया (JSON नहीं मिला)।"),
           ("Return table nahi mila (portal ka format badla ho sakta hai). 'Raw response' dekho.",
            "रिटर्न तालिका नहीं मिली (पोर्टल का फॉर्मैट बदला हो सकता है)। 'Raw response' देखें।"),
           ("Portal se ", "पोर्टल से "), (" record mile par padh nahi paaye. Pehla record: ",
                                          " रिकॉर्ड मिले पर पढ़े नहीं जा सके। पहला रिकॉर्ड: "),
           ("(list khali)", "(सूची खाली)"), ("Internet/portal error: ", "इंटरनेट/पोर्टल त्रुटि: "),
           ("N/A (Composition)", "लागू नहीं (कम्पोज़िशन)"), ("N/A (quarterly)", "लागू नहीं (त्रैमासिक)"),
           ("Composition party", "कम्पोज़िशन पार्टी"), ("Quarterly (QRMP)", "त्रैमासिक (QRMP)"),
           ("NOT FILED", "फाइल नहीं हुआ"), ("Not yet due", "अभी देय नहीं"), ("Abhi due nahi", "अभी देय नहीं"),
           ("Up to date", "अद्यतन"), ("Portal par nahi mila", "पोर्टल पर नहीं मिला"),
           ("koi filing nahi", "कोई फाइलिंग नहीं"), ("din late", "दिन देरी से"), ("Captcha baar-baar galat gaya", "कैप्चा बार-बार गलत गया"), ("Skip kiya", "छोड़ा गया"),
           ("Composition", "कम्पोज़िशन"), ("Monthly", "मासिक"), ("(auto)", "(स्वतः)"), ("pending", "बाकी"),
           ("Filed", "फाइल हुआ"), ("Regular", "नियमित"), ("Active", "सक्रिय"), ("Cancelled", "रद्द"),
           ("Suspended", "निलंबित"), ("due", "देय")],
}
CSV_HDR = {
    "en": {"apna_naam": "own_name", "chuna_mahina": "selected_month", "chuna_gstr1": "selected_gstr1",
           "chuna_gstr3b": "selected_gstr3b"},
    "hi": {"gstin": "GSTIN", "apna_naam": "अपना नाम", "mobile": "मोबाइल", "legal_name": "क़ानूनी नाम",
           "trade_name": "व्यापारिक नाम", "frequency": "रिटर्न प्रकार", "taxpayer_type": "करदाता प्रकार",
           "gst_status": "जीएसटी स्थिति", "registration_date": "पंजीकरण तिथि", "constitution": "संगठन प्रकार",
           "address": "पता", "state_jurisdiction": "राज्य क्षेत्राधिकार", "centre_jurisdiction": "केंद्र क्षेत्राधिकार",
           "cmp08_status": "CMP-08 स्थिति", "gstr4_status": "GSTR-4 स्थिति", "error": "त्रुटि", "note": "टिप्पणी",
           "chuna_mahina": "चुना महीना", "chuna_gstr1": "चुना: GSTR-1", "chuna_gstr3b": "चुना: GSTR-3B",
           "gstr1_latest_period": "GSTR-1 ताज़ा अवधि", "gstr1_filed_on": "GSTR-1 फाइल तिथि",
           "gstr1_days_late": "GSTR-1 देरी (दिन)", "gstr1_status": "GSTR-1 स्थिति",
           "gstr3b_latest_period": "GSTR-3B ताज़ा अवधि", "gstr3b_filed_on": "GSTR-3B फाइल तिथि",
           "gstr3b_days_late": "GSTR-3B देरी (दिन)", "gstr3b_status": "GSTR-3B स्थिति"},
}
FREE_CSV = {"gstin", "apna_naam", "mobile", "legal_name", "trade_name", "address", "state_jurisdiction",
            "centre_jurisdiction", "constitution"}
FREE_X = {"GSTIN", "Party name", "Mobile", "Legal name", "Trade name", "Address", "State jurisdiction",
          "Centre jurisdiction", "Constitution"}


def L(s, lang=None):
    """Dynamic text ko bhasha me badalta hai (hl = jaisa hai). Sirf jaane-pehchane shabd badalte hain."""
    lang = lang or CODE
    if lang == "hl" or not isinstance(s, str):
        return s
    if s in EXACT[lang]:
        return EXACT[lang][s]
    for a, b in PHRASES[lang]:
        s = s.replace(a, b)
    if lang == "hi":
        s = MONTH_RE.sub(lambda m: MONTHS_HI[m[1]], s)
    return s


# ---------------------------------------------------------------- app ke label / button / message
UI = {
    "en": {
        "GST Portal Checker: GSTR-1 & GSTR-3B (captcha manual)": "GST Portal Checker: GSTR-1 & GSTR-3B (manual captcha)",
        "Bhasha / Language:": "Language:",
        "GSTIN list (ek line me ek GSTIN; chaho to 'GSTIN,Q' = quarterly ya 'GSTIN,M' = monthly likho)":
            "GSTIN list (one GSTIN per line; optionally write 'GSTIN,Q' = quarterly or 'GSTIN,M' = monthly)",
        "Start check": "Start check", "CSV se GSTIN load karo": "Load GSTINs from CSV",
        "Report CSV": "Report CSV", "Report Excel": "Report Excel", "Raw response": "Raw response",
        "Saal (FY):": "Year (FY):", "Return type:": "Return type:", "Mahina:": "Month:",
        "Due date badlo": "Change due date", "Auto-submit (6 akshar)": "Auto-submit (6 chars)", "Sirf pending dikhao": "Show pending only",
        "Chhota view (kam columns)": "Compact view (fewer columns)", "Pending ko message": "Message to pending",
        "Error / Skip wale dobara check karo": "Re-check Error / Skipped ones", "Captcha": "Captcha",
        "Start check dabao. Har GSTIN ka captcha yahan aayega.": "Press Start check. The captcha for each GSTIN will appear here.",
        "(captcha yahan dikhega)": "(captcha will appear here)", "Submit (Enter)": "Submit (Enter)",
        "Naya captcha": "New captcha", "Skip": "Skip", "Captcha size:": "Captcha size:",
        "Row par double-click: mahine-wise status.  Right-click: is party ko Monthly / Quarterly (QRMP) / Auto maano.":
            "Double-click a row: month-wise status.  Right-click: treat this party as Monthly / Quarterly (QRMP) / Auto.",
        "Is party ko Monthly maano": "Treat this party as Monthly",
        "Is party ko Quarterly (QRMP) maano": "Treat this party as Quarterly (QRMP)",
        "Auto (andaza)": "Auto (guess)", "Sab Monthly": "All Monthly", "Sab Quarterly (QRMP)": "All Quarterly (QRMP)",
        "Sab mahine": "All months",
        "Party name": "Party name", "Type": "Type", "GSTR-1 latest": "GSTR-1 latest", "GSTR-1 status": "GSTR-1 status",
        "GSTR-3B latest": "GSTR-3B latest", "GSTR-3B status": "GSTR-3B status",
        "Composition: CMP-08": "Composition: CMP-08", "Chuna mahina: GSTR-1": "Selected month: GSTR-1",
        "Chuna mahina: GSTR-3B": "Selected month: GSTR-3B", "Note": "Note",
        "Naye saal ka data laane ke liye Start check dobara dabao.": "Press Start check again to fetch data for the new year.",
        "Pehle GSTIN daalo.": "Enter GSTINs first.", "{n} duplicate GSTIN hata diye.": "Removed {n} duplicate GSTIN(s).",
        "(ho gaya)": "(done)", "Ho gaya: {n} GSTIN. Report CSV / Excel save kar sakte ho.":
            "Done: {n} GSTIN. You can save the report as CSV / Excel.",
        "{g} ({i}/{n}): captcha la raha hoon…": "{g} ({i}/{n}): fetching captcha…",
        "{g} ({i}/{n}): captcha type karke Enter dabao.": "{g} ({i}/{n}): type the captcha and press Enter.",
        "Captcha alag window me khula hai": "Captcha opened in a separate window",
        "Captcha nahi aaya: {msg}  ('Naya captcha' dabao)": "Captcha did not load: {msg}  (press 'New captcha')",
        "{g}: check ho raha hai…": "{g}: checking…", "Captcha galat tha. Naya captcha la raha hoon…":
            "Captcha was wrong. Fetching a new one…",
        "{g}: month-wise status ({t})": "{g}: month-wise status ({t})", "Return": "Return", "Period": "Period",
        "Status": "Status", "Raw portal response (debugging)": "Raw portal response (debugging)",
        "Abhi koi response nahi hai.": "No response yet.",
        "Sarkar ne kisi mahine ki due date badhayi ho to yahan daalo.\nHisaab (late / NOT FILED) apne aap naye sire se hoga.":
            "If the government has extended a due date, enter it here.\nLate / NOT FILED will be recalculated automatically.",
        "Mahina": "Month", "Kis par": "Applies to", "Nayi due date (dd-mm-yyyy):": "New due date (dd-mm-yyyy):",
        "Add / Badlo": "Add / Change", "Chuni hui hatao": "Remove selected",
        "Date dd-mm-yyyy me daalo (jaise 25-10-2026) aur mahina chuno.":
            "Enter the date as dd-mm-yyyy (e.g. 25-10-2026) and choose a month.",
        "Dono (Monthly + QRMP)": "Both (Monthly + QRMP)", "Sirf Monthly": "Monthly only",
        "Sirf Quarterly (QRMP)": "Quarterly (QRMP) only",
        "Pichla kaam mila: {done} GSTIN ho chuke hain, {left} baaki hain.\nWahin se aage badhein? (Nahi dabaoge to naya kaam shuru karne par ye hat jayega.)":
            "Previous work found: {done} GSTIN done, {left} left.\nContinue from there? (If you choose No, it will be discarded when you start new work.)",
        "Pichla result wapas aa gaya: {done} GSTIN. Report save kar sakte ho.":
            "Previous results restored: {done} GSTIN. You can save the report.",
        "Dobara check karne layak koi error / skip wali party nahi hai.": "There is no errored / skipped party to re-check.",
        "Abhi koi pending party nahi hai.": "There is no pending party right now.",
        "Pending parties ko message (WhatsApp)": "Message to pending parties (WhatsApp)",
        "Aapki firm ka naam (message ke neeche aayega):": "Your firm name (added at the bottom of the message):",
        "(mobile hai)": "(has mobile)", "(mobile nahi)": "(no mobile)",
        "Ye message copy karo": "Copy this message", "WhatsApp me kholo": "Open in WhatsApp",
        "Sab messages copy karo": "Copy all messages",
        "Message copy ho gaya. WhatsApp me paste karo.": "Message copied. Paste it in WhatsApp.",
        "Is party ka mobile number nahi hai. Message copy karke khud bhejo.":
            "This party has no mobile number. Copy the message and send it yourself.",
        "Pehle check chalao.": "Run the check first.", "CSV report save hui: {p}": "CSV report saved: {p}",
        "Excel report save hui: {p}": "Excel report saved: {p}",
        "Save nahi hui (file kahin khuli hai?): {e}": "Could not save (is the file open somewhere?): {e}",
        "Bhasha badal di gayi hai.": "Language changed.",
    },
    "hi": {
        "GST Portal Checker: GSTR-1 & GSTR-3B (captcha manual)": "जीएसटी पोर्टल चेकर: GSTR-1 और GSTR-3B (कैप्चा हाथ से)",
        "Bhasha / Language:": "भाषा / Language:",
        "GSTIN list (ek line me ek GSTIN; chaho to 'GSTIN,Q' = quarterly ya 'GSTIN,M' = monthly likho)":
            "GSTIN सूची (हर पंक्ति में एक GSTIN; चाहें तो 'GSTIN,Q' = त्रैमासिक या 'GSTIN,M' = मासिक लिखें)",
        "Start check": "जाँच शुरू करें", "CSV se GSTIN load karo": "CSV से GSTIN लोड करें",
        "Report CSV": "रिपोर्ट CSV", "Report Excel": "रिपोर्ट Excel", "Raw response": "कच्चा जवाब (Raw)",
        "Saal (FY):": "वर्ष (FY):", "Return type:": "रिटर्न प्रकार:", "Mahina:": "महीना:",
        "Due date badlo": "देय तारीख बदलें", "Auto-submit (6 akshar)": "ऑटो-सबमिट (6 अक्षर)", "Sirf pending dikhao": "सिर्फ़ बाकी (पेंडिंग) दिखाएँ",
        "Chhota view (kam columns)": "छोटा व्यू (कम कॉलम)", "Pending ko message": "पेंडिंग को संदेश",
        "Error / Skip wale dobara check karo": "त्रुटि / छोड़े गए दोबारा जाँचें", "Captcha": "कैप्चा",
        "Start check dabao. Har GSTIN ka captcha yahan aayega.": "'जाँच शुरू करें' दबाएँ। हर GSTIN का कैप्चा यहाँ आएगा।",
        "(captcha yahan dikhega)": "(कैप्चा यहाँ दिखेगा)", "Submit (Enter)": "जमा करें (Enter)",
        "Naya captcha": "नया कैप्चा", "Skip": "छोड़ें", "Captcha size:": "कैप्चा आकार:",
        "Row par double-click: mahine-wise status.  Right-click: is party ko Monthly / Quarterly (QRMP) / Auto maano.":
            "पंक्ति पर डबल-क्लिक: महीनेवार स्थिति।  राइट-क्लिक: इस पार्टी को मासिक / त्रैमासिक (QRMP) / ऑटो मानें।",
        "Is party ko Monthly maano": "इस पार्टी को मासिक मानें",
        "Is party ko Quarterly (QRMP) maano": "इस पार्टी को त्रैमासिक (QRMP) मानें",
        "Auto (andaza)": "ऑटो (अनुमान)", "Sab Monthly": "सभी मासिक", "Sab Quarterly (QRMP)": "सभी त्रैमासिक (QRMP)",
        "Sab mahine": "सभी महीने",
        "Party name": "पार्टी का नाम", "Type": "प्रकार", "GSTR-1 latest": "GSTR-1 ताज़ा", "GSTR-1 status": "GSTR-1 स्थिति",
        "GSTR-3B latest": "GSTR-3B ताज़ा", "GSTR-3B status": "GSTR-3B स्थिति",
        "Composition: CMP-08": "कम्पोज़िशन: CMP-08", "Chuna mahina: GSTR-1": "चुना महीना: GSTR-1",
        "Chuna mahina: GSTR-3B": "चुना महीना: GSTR-3B", "Note": "टिप्पणी",
        "Naye saal ka data laane ke liye Start check dobara dabao.": "नए वर्ष का डेटा लाने के लिए 'जाँच शुरू करें' दोबारा दबाएँ।",
        "Pehle GSTIN daalo.": "पहले GSTIN डालें।", "{n} duplicate GSTIN hata diye.": "{n} दोहराए गए GSTIN हटा दिए गए।",
        "(ho gaya)": "(हो गया)", "Ho gaya: {n} GSTIN. Report CSV / Excel save kar sakte ho.":
            "हो गया: {n} GSTIN। रिपोर्ट CSV / Excel में सेव कर सकते हैं।",
        "{g} ({i}/{n}): captcha la raha hoon…": "{g} ({i}/{n}): कैप्चा ला रहा हूँ…",
        "{g} ({i}/{n}): captcha type karke Enter dabao.": "{g} ({i}/{n}): कैप्चा टाइप करके Enter दबाएँ।",
        "Captcha alag window me khula hai": "कैप्चा अलग विंडो में खुला है",
        "Captcha nahi aaya: {msg}  ('Naya captcha' dabao)": "कैप्चा नहीं आया: {msg}  ('नया कैप्चा' दबाएँ)",
        "{g}: check ho raha hai…": "{g}: जाँच हो रही है…", "Captcha galat tha. Naya captcha la raha hoon…":
            "कैप्चा गलत था। नया कैप्चा ला रहा हूँ…",
        "{g}: month-wise status ({t})": "{g}: महीनेवार स्थिति ({t})", "Return": "रिटर्न", "Period": "अवधि",
        "Status": "स्थिति", "Raw portal response (debugging)": "पोर्टल का कच्चा जवाब (डिबगिंग)",
        "Abhi koi response nahi hai.": "अभी कोई जवाब नहीं है।",
        "Sarkar ne kisi mahine ki due date badhayi ho to yahan daalo.\nHisaab (late / NOT FILED) apne aap naye sire se hoga.":
            "यदि सरकार ने किसी महीने की देय तारीख बढ़ाई हो तो यहाँ डालें।\nदेरी / फाइल नहीं हुआ का हिसाब अपने आप नए सिरे से होगा।",
        "Mahina": "महीना", "Kis par": "किस पर", "Nayi due date (dd-mm-yyyy):": "नई देय तारीख (dd-mm-yyyy):",
        "Add / Badlo": "जोड़ें / बदलें", "Chuni hui hatao": "चुनी हुई हटाएँ",
        "Date dd-mm-yyyy me daalo (jaise 25-10-2026) aur mahina chuno.":
            "तारीख dd-mm-yyyy में डालें (जैसे 25-10-2026) और महीना चुनें।",
        "Dono (Monthly + QRMP)": "दोनों (मासिक + QRMP)", "Sirf Monthly": "सिर्फ़ मासिक",
        "Sirf Quarterly (QRMP)": "सिर्फ़ त्रैमासिक (QRMP)",
        "Pichla kaam mila: {done} GSTIN ho chuke hain, {left} baaki hain.\nWahin se aage badhein? (Nahi dabaoge to naya kaam shuru karne par ye hat jayega.)":
            "पिछला काम मिला: {done} GSTIN हो चुके हैं, {left} बाकी हैं।\nवहीं से आगे बढ़ें? (नहीं चुनने पर नया काम शुरू करते ही यह हट जाएगा।)",
        "Pichla result wapas aa gaya: {done} GSTIN. Report save kar sakte ho.":
            "पिछला परिणाम वापस आ गया: {done} GSTIN। रिपोर्ट सेव कर सकते हैं।",
        "Dobara check karne layak koi error / skip wali party nahi hai.": "दोबारा जाँचने लायक कोई त्रुटि / छोड़ी गई पार्टी नहीं है।",
        "Abhi koi pending party nahi hai.": "अभी कोई पेंडिंग पार्टी नहीं है।",
        "Pending parties ko message (WhatsApp)": "पेंडिंग पार्टियों को संदेश (WhatsApp)",
        "Aapki firm ka naam (message ke neeche aayega):": "आपकी फर्म का नाम (संदेश के नीचे आएगा):",
        "(mobile hai)": "(मोबाइल है)", "(mobile nahi)": "(मोबाइल नहीं)",
        "Ye message copy karo": "यह संदेश कॉपी करें", "WhatsApp me kholo": "WhatsApp में खोलें",
        "Sab messages copy karo": "सभी संदेश कॉपी करें",
        "Message copy ho gaya. WhatsApp me paste karo.": "संदेश कॉपी हो गया। WhatsApp में पेस्ट करें।",
        "Is party ka mobile number nahi hai. Message copy karke khud bhejo.":
            "इस पार्टी का मोबाइल नंबर नहीं है। संदेश कॉपी करके खुद भेजें।",
        "Pehle check chalao.": "पहले जाँच चलाएँ।", "CSV report save hui: {p}": "CSV रिपोर्ट सेव हुई: {p}",
        "Excel report save hui: {p}": "Excel रिपोर्ट सेव हुई: {p}",
        "Save nahi hui (file kahin khuli hai?): {e}": "सेव नहीं हुई (क्या फ़ाइल कहीं खुली है?): {e}",
        "Bhasha badal di gayi hai.": "भाषा बदल दी गई है।",
    },
}


UI["en"].update({
    "Aakhri {n} GSTIN ka check chal raha hai…": "Last {n} GSTIN are still being checked…",
    "{g}: captcha galat tha, ise baad me dobara poochenge.": "{g}: captcha was wrong; it will be asked again later.",
    "Pehle chal rahe check poore hone do, phir dobara check karo.": "Let the running checks finish first, then re-check.",
    "GST Return Status Checker": "GST Return Status Checker",
    "Bina API key; captcha aap type karte ho": "No API key needed; you type the captcha",
    "Report PDF": "Report PDF", "Firm ki jaankari": "Firm details",
    "Firm ki jaankari (report me aayegi)": "Firm details (shown in reports)",
    "Firm ka naam:": "Firm name:", "Pata / phone:": "Address / phone:", "Report banane wala (naam):": "Prepared by (name):",
    "Logo (PNG / JPG):": "Logo (PNG / JPG):", "Chuno…": "Browse…", "Save karo": "Save", "Logo hatao": "Remove logo",
    "Firm ki jaankari save ho gayi.": "Firm details saved.",
    "PDF report: browser me Print dialog khulega. 'Save as PDF' chuno. File: {p}":
        "PDF report: the browser will open the Print dialog. Choose 'Save as PDF'. File: {p}",
    "Kul: {t}  |  Baaki (pending): {p}  |  Theek: {o}  |  Error: {e}": "Total: {t}  |  Pending: {p}  |  OK: {o}  |  Error: {e}",
    "  |  Check ho rahe: {n}": "  |  Checking: {n}",
    "Thoda ruko: {n} GSTIN abhi check ho rahe hain. Kuch der baad Enter dabao.":
        "Please wait: {n} GSTIN are still being checked. Press Enter again in a moment.",
    "Aakhri {n} GSTIN check ho rahe hain…": "Last {n} GSTIN are being checked…",
    "Captcha galat tha ({g}). Naya captcha la raha hoon…": "Captcha for {g} was wrong. Fetching a new one…",
    "Report save nahi hui: {e}": "Could not save the report: {e}",
})
UI["hi"].update({
    "Aakhri {n} GSTIN ka check chal raha hai…": "आख़िरी {n} GSTIN की जाँच चल रही है…",
    "{g}: captcha galat tha, ise baad me dobara poochenge.": "{g}: कैप्चा गलत था; इसे बाद में दोबारा पूछेंगे।",
    "Pehle chal rahe check poore hone do, phir dobara check karo.": "पहले चल रही जाँच पूरी होने दें, फिर दोबारा जाँचें।",
    "GST Return Status Checker": "जीएसटी रिटर्न स्थिति जाँच",
    "Bina API key; captcha aap type karte ho": "API key की ज़रूरत नहीं; कैप्चा आप टाइप करते हैं",
    "Report PDF": "रिपोर्ट PDF", "Firm ki jaankari": "फर्म की जानकारी",
    "Firm ki jaankari (report me aayegi)": "फर्म की जानकारी (रिपोर्ट में आएगी)",
    "Firm ka naam:": "फर्म का नाम:", "Pata / phone:": "पता / फ़ोन:", "Report banane wala (naam):": "रिपोर्ट बनाने वाला (नाम):",
    "Logo (PNG / JPG):": "लोगो (PNG / JPG):", "Chuno…": "चुनें…", "Save karo": "सेव करें", "Logo hatao": "लोगो हटाएँ",
    "Firm ki jaankari save ho gayi.": "फर्म की जानकारी सेव हो गई।",
    "PDF report: browser me Print dialog khulega. 'Save as PDF' chuno. File: {p}":
        "PDF रिपोर्ट: ब्राउज़र में प्रिंट विंडो खुलेगी। 'Save as PDF' चुनें। फ़ाइल: {p}",
    "Kul: {t}  |  Baaki (pending): {p}  |  Theek: {o}  |  Error: {e}": "कुल: {t}  |  बाकी (पेंडिंग): {p}  |  ठीक: {o}  |  त्रुटि: {e}",
    "  |  Check ho rahe: {n}": "  |  जाँच हो रही: {n}",
    "Thoda ruko: {n} GSTIN abhi check ho rahe hain. Kuch der baad Enter dabao.":
        "थोड़ा रुकें: {n} GSTIN की जाँच चल रही है। कुछ देर बाद Enter दबाएँ।",
    "Aakhri {n} GSTIN check ho rahe hain…": "आख़िरी {n} GSTIN की जाँच हो रही है…",
    "Captcha galat tha ({g}). Naya captcha la raha hoon…": "{g} का कैप्चा गलत था। नया कैप्चा ला रहा हूँ…",
    "Report save nahi hui: {e}": "रिपोर्ट सेव नहीं हुई: {e}",
})


def T(s, **kw):
    """App ka text chuni hui bhasha me. Table me na ho to Hinglish original hi dikhta hai."""
    t = s if CODE == "hl" else UI.get(CODE, {}).get(s, s)
    return t.format(**kw) if kw else t
