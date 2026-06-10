---
name: s138_complaint
description: Criminal complaint for cheque dishonour under S.138 NI Act — S.141 liability, exhibit registry, affidavit.
trigger_keywords: [138 complaint, s138 complaint, s.138, ni act complaint, cheque dishonour complaint, cheque bounce complaint, negotiable instruments complaint, dishonoured cheque, cheque return, section 138]
matter_types: [s138_complaint, s138, cheque_dishonour]
jurisdiction: [Indian criminal courts — CJM / JMFC]
---

# S.138 NI Act Complaint Skill

## Governing Law
Negotiable Instruments Act, 1881 — Sections 138, 141, 142, 143.
Summary trial under Section 143 NI Act.

## Document Type
Criminal complaint filed before Chief Judicial Magistrate (CJM) or Judicial Magistrate First Class (JMFC).

## Party Labels
- Filer: **Complainant**
- Opposing: **Accused**
- Never use "Petitioner" or "Respondent" — those are writ-petition labels.

## Mandatory Intake Before Drafting
Confirm all of the following before generating the draft:
- [ ] Complainant's full name, address, business description
- [ ] Accused's full name, address, and **entity type** (individual / proprietorship / partnership / company)
- [ ] If accused is a firm/company: name of firm + name of person in charge (for S.141)
- [ ] Transaction: nature of goods/services/loan, date, invoice number, amount
- [ ] Part payments made by accused (if any) and outstanding amount
- [ ] Cheque number, bank name, branch, account number, amount in figures and words, date
- [ ] First dishonour: presentation date, return memo number, return memo date, reason (e.g. "Insufficient Funds" / "Drawers Signature Differs")
- [ ] Second dishonour (if any): same fields
- [ ] Demand notice: date sent, mode of service (Speed Post / WhatsApp / email), demand amount
- [ ] Notice compliance deadline (notice date + 15 days) and whether accused complied
- [ ] Presenting bank branch location (for S.142(2) jurisdiction)

## Required Sections (in this exact order)

```
1.  court_header        → Formal court name (from SOUL.md court_name_formal or jurisdiction field)
2.  case_number         → "COMPLAINT CASE NO. _____ OF ____" (leave blank — court fills)
3.  cause_title         → Complainant name ... COMPLAINANT / Accused name ... ACCUSED
4.  opening_declaration → "COMPLAINT UNDER SECTION 138 READ WITH SECTION 142 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881"
5.  memo_of_parties     → Full names, addresses, mobile numbers, relationship
6.  para_complainant    → Identity and business of complainant
7.  para_accused        → Identity and business of accused, relationship to complainant
8.  para_transaction    → Goods/services/loan giving rise to the legally enforceable debt
9.  para_cheque         → Cheque number, bank, account, amount (figures + words), date, purpose
10. para_first_dishonour → Presentation date, return memo number + date, dishonour reason
11. para_demand_notice  → Date of notice, mode of service, 15-day demand period, total demanded
12. para_non_compliance → Accused's failure to pay within statutory 15-day period
13. para_second_dishonour → [CONDITIONAL: include only if second dishonour facts are provided]
14. para_s141_liability → [CONDITIONAL: include if accused_entity_type ≠ individual — see S.141 block below]
15. para_cause_of_action → Date on which cause of action crystallised (day after compliance deadline)
16. para_jurisdiction   → S.142(2): court with jurisdiction over branch where cheque was presented
17. para_limitation     → S.142(b): complaint filed within 30 days of expiry of notice period
18. prayer              → 4 reliefs: (a) cognizance; (b) conviction + fine = twice cheque amount; (c) S.357 compensation; (d) costs
19. verification        → Complainant's verification — first person, date, place
```

## Section-by-Section Drafting Instructions

### para_complainant (para 1)
> "That the Complainant, [name], is a [individual/proprietary concern/company] engaged in the business of [description]. The Complainant is a person of repute and has been conducting business honestly and lawfully."

### para_accused (para 2)
> "That the Accused, [name], is a [individual/proprietor of M/s. X / partner of M/s. X / director of X Ltd.] engaged in the business of [description]. The Accused is personally known to the Complainant."

### para_transaction (para 3)
> "That the Complainant supplied [goods/rendered services/advanced a loan] to the Accused vide Invoice No. [X] dated [date] for a total consideration of Rs. [amount] (Rupees [words] only). The Accused received the said [goods/services/amount] and the said sum constitutes a legally enforceable debt/liability."

If part payments were made:
> "That the Accused made part payments of Rs. [amount] on [dates], leaving an outstanding legally enforceable debt of Rs. [outstanding_amount] (Rupees [words] only)."

### para_cheque (para 4)
> "That in discharge of the said legally enforceable liability, the Accused issued Cheque No. [number] dated [date] drawn on [Bank Name], [Branch], Account No. [account], for a sum of Rs. [amount] (Rupees [words] only) in favour of the Complainant."

### para_first_dishonour (para 5)
> "That the Complainant presented the aforesaid cheque through his banker for encashment on [presentation_date]. The said cheque was returned unpaid by the bank vide Return Memo No. [number] dated [date] with the remark '[dishonour_reason]'."

**For "Drawers Signature Differs" dishonour:** cite *M/s Laxmi Dyechem v. State of Gujarat & Ors.* [2012] 11 SCR 466, which holds that signature mismatch amounts to dishonour within the meaning of S.138. Include:
> "It is submitted that 'Drawers Signature Differs' constitutes dishonour within the meaning of Section 138 NI Act. Reference is made to M/s Laxmi Dyechem v. State of Gujarat & Ors. [2012] 11 SCR 466 wherein the Hon'ble Supreme Court has held that any return of a cheque other than for want of funds is also covered under Section 138."

### para_demand_notice (para 6)
> "That as required under the proviso to Section 138 of the NI Act, the Complainant caused a legal notice dated [notice_date] to be served on the Accused through [Speed Post / WhatsApp / e-mail / all modes], demanding payment of Rs. [amount] within 15 days of receipt of the notice. The Accused received/was deemed to have received the said notice on [receipt_date]. The statutory period of 15 days expired on [compliance_deadline]."

### para_non_compliance (para 7)
> "That despite receipt of the aforesaid notice and the expiry of the statutory period of 15 days, the Accused has failed, neglected, and refused to pay the said amount to the Complainant. The accused has not made any payment whatsoever till date."

### para_s141_liability (CONDITIONAL — include only if accused is NOT an individual)

**Trigger:** `accused_entity_type` is "proprietorship", "partnership", or "company".

**For proprietorship:**
> "That the Accused No. [n], [proprietor_name], was at all material times the sole proprietor of M/s. [firm_name], and was personally responsible for and in charge of the day-to-day conduct of the business of the said firm. The Accused is therefore liable under Section 138 read with Section 141 of the Negotiable Instruments Act, 1881."

**For partnership:**
> "That the Accused No. [n], [partner_name], was at all material times a partner of M/s. [firm_name] and was personally responsible for the conduct of business of the said firm. All partners are jointly and severally liable under Section 138 read with Section 141 of the Negotiable Instruments Act, 1881."

**For company:**
> "That the Accused No. [n], [director_name], was at all material times a Director of [company_name] and was responsible for the conduct of the business of the company at the time the offence was committed. The said person is therefore liable under Section 138 read with Section 141 of the Negotiable Instruments Act, 1881."

### para_cause_of_action (para, after s141 if present)
> "That the cause of action in the present complaint arose on [day after compliance deadline], when the Accused failed to pay the amount demanded within the statutory period of 15 days after receipt of the legal notice, at [city/court location]."

### para_jurisdiction (S.142(2))
> "That the present complaint is filed before this Hon'ble Court as the cheque in question was delivered for collection to [Bank Name], [Branch], [City/District], which falls within the territorial jurisdiction of this Hon'ble Court, as per Section 142(2) of the Negotiable Instruments Act, 1881."

### para_limitation (S.142(b))
> "That the present complaint is filed within the period of 30 days from the date on which the cause of action arose under the first proviso to Section 138, as required under Section 142(b) of the Negotiable Instruments Act, 1881. The complaint is therefore within limitation."

### prayer
```
PRAYER

In view of the above facts and circumstances, it is most humbly prayed that this
Hon'ble Court may be pleased to:

(a) Take cognizance of the offence committed by the Accused under Section 138
    of the Negotiable Instruments Act, 1881, and issue process/summons against
    the Accused;

(b) Upon conviction, award sentence of imprisonment and direct payment of fine
    equivalent to twice the amount of the cheque i.e. Rs. [cheque_amount × 2]/-
    (Rupees [words] only), as envisaged under Section 138 NI Act;

(c) Direct the Accused to pay the said amount of Rs. [cheque_amount × 2]/-
    as compensation to the Complainant under Section 357 of the Code of
    Criminal Procedure, 1973;

(d) Award costs of the present proceedings to the Complainant;

And/or pass any other order(s) as this Hon'ble Court may deem fit in the
interest of justice.
```

### verification
```
VERIFICATION

I, [complainant_name], [occupation], [address], do hereby solemnly affirm and
verify that the contents of this complaint are true and correct to the best of
my knowledge and belief. Nothing material has been concealed therefrom.

Verified at [city] on this _____ day of _________, 20___.

[Signature]
Complainant
```

## Exhibit Registry (Standard Labels)

Use EX-CW1/A format throughout — in the complaint body, affidavit, and list of documents.
Never mix "Annexure A" with "EX-CW1/A" in the same filing packet.

| Document | Label |
|----------|-------|
| Invoice / agreement giving rise to debt | EX-CW1/A |
| Cheque (original or photocopy) | EX-CW1/B |
| Return Memo — first dishonour | EX-CW1/C |
| Demand notice | EX-CW1/D |
| Postal receipt / speed post tracking / WhatsApp screenshot | EX-CW1/E |
| Return Memo — second dishonour (if any) | EX-CW1/F |
| Part payment receipts (if any) | EX-CW1/G |
| Additional correspondence (emails, WhatsApp) | EX-CW1/H |

## Sub-Documents Required for Filing Packet

1. **list_of_documents.docx** — exhibit register with EX-CW1/A labels and descriptions
2. **affidavit_evidence.docx** — sworn testimony by complainant, 12–14 numbered paragraphs, first person, with exhibit cross-references (CW-1)
3. **witness_list.docx** — CW-1 (complainant, proves all facts) + SBI/bank officials (prove return memo)
4. **vakalatnama.docx** — power of attorney from client to advocate (filed separately at counter)

## Key Authorities

| Case | Citation | Proposition |
|------|----------|-------------|
| M/s Laxmi Dyechem v. State of Gujarat & Ors. | [2012] 11 SCR 466 | "Drawers Signature Differs" is dishonour within S.138 |
| Dashrath Rupsingh Rathod v. State of Maharashtra | (2014) 9 SCC 129 | Jurisdiction: court where cheque was presented for collection |
| Meters and Instruments Pvt. Ltd. v. Kanchan Mehta | (2018) 1 SCC 560 | Summary trial; complainant's affidavit is examination-in-chief |
| Dalmia Cement (Bharat) Ltd. v. Galaxy Traders | (2001) 6 SCC 463 | Legally enforceable debt is essential; personal relationship insufficient |

## Computed Fields (Do Not Let LLM Calculate These)

These must be arithmetic, not LLM-generated prose:
- `notice_compliance_deadline` = `notice_date` + 15 days
- `limitation_deadline` = `notice_compliance_deadline` + 30 days
- `prayer_fine_amount` = `cheque_amount` × 2 (state in figures AND words)
- `cause_of_action_date` = day after `notice_compliance_deadline`

## Common Errors to Avoid

1. **Wrong party labels**: Never use "Petitioner" / "Respondent" — always "Complainant" / "Accused"
2. **Missing S.141**: If accused is a proprietor/partner/director, the S.141 paragraph is mandatory
3. **"Appropriate fine" in prayer**: Always specify "fine equivalent to twice the cheque amount = Rs. X"
4. **Generic exhibit labels**: Always use EX-CW1/A format, never "Annexure A"
5. **Vakalatnama in complaint body**: The vakalatnama is filed separately at the counter — do not embed it
6. **Lawyer notes in filing body**: Plain English Summary and Risk Assessment must NOT appear in the .docx
7. **Missing limitation paragraph citing S.142(b)**: Always cite the sub-section explicitly
8. **Missing jurisdiction paragraph citing S.142(2)**: Always state the presenting bank's branch and district
