# Pleading Blueprints

_How lawyers actually think. For each major Indian court document type: required blocks, optional blocks, ordering rules, and dependencies on specific facts._

_These blueprints are the specification for the Pleading Schema Registry (Layer B in `court_draft_architecture.md`). They should drive the LLM's draft instruction, the review node's structural checks, and the filing package builder's sub-document list._

---

## The Lawyer's Mental Model

A lawyer does not think "write paragraphs." A lawyer thinks:

```
What happened?        → facts
Who is liable?        → issues + burden
What can I prove?     → evidence + exhibits
What procedure?       → jurisdiction + limitation + forum
What do I want?       → prayer
```

Every pleading is an answer to these five questions in roughly this order, with jurisdiction-specific packaging around them.

---

## Blueprint 1 — S.138 NI Act Complaint (Criminal)

**Court:** Chief Judicial Magistrate (for cheque amounts ≤ ₹2L typically) or JMFC  
**Governing law:** Negotiable Instruments Act, 1881 (S.138, S.141, S.142, S.143)  
**Procedure:** Summary trial under S.143 NI Act

### Required Sections (in filing order)

| # | Section ID | Content | Mandatory | Depends On |
|---|-----------|---------|-----------|-----------|
| 1 | `court_header` | Full formal court name + bench designation | Yes | `court_name` from SOUL.md |
| 2 | `case_number` | "COMPLAINT CASE NO. ___ OF ____" | Yes | Leave blank |
| 3 | `cause_title` | Complainant name ... Complainant / Accused names ... Accused | Yes | `parties` |
| 4 | `opening_declaration` | "COMPLAINT UNDER SECTION 138 READ WITH SECTION 142 OF THE NI ACT, 1881" | Yes | — |
| 5 | `memo_of_parties` | Full names, addresses, mobile numbers, relationship | Yes | `parties` with addresses |
| 6 | `para_complainant` | Identity and business of complainant | Yes | `parties.complainant` |
| 7 | `para_accused` | Identity and business of accused, relationship to complainant | Yes | `parties.accused` |
| 8 | `para_transaction` | Goods/services/loan giving rise to the legally enforceable debt | Yes | `transaction_facts` |
| 9 | `para_cheque` | Cheque number, bank, account, amount (figures + words), date, purpose of issue | Yes | `cheque_facts` |
| 10 | `para_first_dishonour` | Presentation date, return memo number + date, reason for dishonour | Yes | `dishonour_1_facts` |
| 11 | `para_demand_notice` | Date of notice, mode of service, 15-day demand period, total amount demanded | Yes | `notice_facts` |
| 12 | `para_non_compliance` | Accused's failure to pay within statutory period | Yes | `notice_facts.compliance_deadline` |
| 13 | `para_second_dishonour` | Second presentation, second return memo, same/different reason | No | `dishonour_2_facts` |
| 14 | `para_s141_liability` | Entity type of accused + personal responsibility + joint & several liability | Conditional | `accused_entity_type != "individual"` |
| 15 | `para_cause_of_action` | Date on which cause of action crystallised + location | Yes | `cause_of_action_date` |
| 16 | `para_jurisdiction` | S.142(2): court where cheque was delivered for collection | Yes | `presenting_bank_branch` + `court_location` |
| 17 | `para_limitation` | S.142(b): complaint within 30 days of expiry of notice period | Yes | `notice_compliance_deadline` |
| 18 | `prayer` | (a) cognizance/process; (b) conviction + fine = twice cheque amount; (c) costs | Yes | `cheque_amount` for (b) |
| 19 | `verification` | Complainant's verification — first person, date, place | Yes | `parties.complainant.name` |

### Sub-Documents (required for filing packet)

| Document | Purpose | Mandatory |
|----------|---------|-----------|
| `list_of_documents.docx` | Exhibit register with EX-CW1/A labels | Yes |
| `affidavit_evidence.docx` | Sworn testimony by complainant, first person, 12–14 paras | Yes |
| `witness_list.docx` | CW-1 (complainant) + bank officials (for return memo authenticity) | Yes |
| `vakalatnama.docx` | Power of attorney from client to advocate | Yes (filed at counter) |

### Exhibit Registry (standard for S.138 complaint)

| Exhibit | Label | Description |
|---------|-------|-------------|
| Invoice / agreement | EX-CW1/A | Document giving rise to the debt |
| Cheque (original or photocopy) | EX-CW1/B | The dishonoured instrument |
| Return Memo 1 | EX-CW1/C | Bank's return memo for first dishonour |
| Demand Notice | EX-CW1/D | Lawyer's notice to accused |
| Postal receipt / tracking | EX-CW1/E | Proof of service of notice |
| Return Memo 2 (if second dishonour) | EX-CW1/F | Second return memo |
| Any payment receipts | EX-CW1/G | Part payments made by accused |
| Additional correspondence | EX-CW1/H | WhatsApp screenshots, emails, etc. |

### Ordering Rules
- Memo of Parties always before body paragraphs
- Para_s141_liability always after Para_accused and before Para_cause_of_action
- Cause of Action always before Jurisdiction and Limitation
- Prayer always last before Verification
- Affidavit-in-evidence is a separate document — NOT a section of the complaint

### Key Dependencies (computed, not LLM-generated)
- `limitation_deadline` = `notice_compliance_deadline` + 30 days
- `prayer_b_amount` = `cheque_amount` × 2 (formatted in figures + words)
- `jurisdiction_court` = court in the district where the presenting bank's branch is located

---

## Blueprint 2 — Written Statement (Civil, CPC O.VIII)

**Court:** Civil court (suit court)  
**Governing law:** CPC 1908, O.VIII; Limitation Act 1963  

### Required Sections (in filing order)

| # | Section ID | Content | Mandatory |
|---|-----------|---------|-----------|
| 1 | `court_header` | Full court name | Yes |
| 2 | `suit_details` | Suit No., year, parties | Yes |
| 3 | `opening` | "WRITTEN STATEMENT ON BEHALF OF DEFENDANT NO. __" | Yes |
| 4 | `preliminary_objections` | Limitation bar, non-maintainability, jurisdiction objections | Yes |
| 5 | `para_admissions_denials` | Para-by-para response tracking plaintiff's numbering | Yes |
| 6 | `affirmative_defences` | Positive case of defendant | Yes |
| 7 | `counterclaim` | If any — separate application under O.VIII R.6A | No |
| 8 | `prayer` | Dismissal of suit + costs | Yes |
| 9 | `verification` | Defendant's verification | Yes |

### Critical Ordering Rule
Preliminary objections ALWAYS first — before admissions/denials. If a jurisdiction objection exists, it must appear before any admission on merits or it is waived. Para-by-para response must track the plaint's numbering: if the plaint has Para 4, the WS must have a response to Para 4, not skip to Para 5.

### Dependencies
- `plaint_paras` — must have the plaint to number responses correctly
- `limitation_analysis` — needed for preliminary objection on limitation

---

## Blueprint 3 — Bail Application (CrPC / BNSS)

**Court:** JMFC (S.436/437), Sessions Court (S.439), HC (S.439 + Art.226)  
**Governing law:** CrPC/BNSS S.436–439

### Required Sections

| # | Section ID | Content | Mandatory |
|---|-----------|---------|-----------|
| 1 | `court_header` | Court name + designation | Yes |
| 2 | `matter_particulars` | FIR No., Police Station, date, sections invoked | Yes |
| 3 | `accused_particulars` | Name, age, address, custody date, remand orders | Yes |
| 4 | `brief_facts` | 3–5 paras on facts — accused's version | Yes |
| 5 | `grounds_for_bail` | 5–8 numbered grounds in descending weight | Yes |
| 6 | `prayer` | Release on bail with or without surety; conditions if any | Yes |
| 7 | `verification` | Advocate signs, not accused | Varies |

### Grounds Ordering Rule (descending weight)
1. First-time offender / no prior criminal antecedents
2. Cooperation with investigation
3. Deep roots in community / no flight risk
4. No tampering of witnesses / evidence
5. Medical grounds (if applicable)
6. Employment / family dependents
7. Co-accused on bail (parity argument)
8. Merits of the case (nature of offence)

**Critical:** Leading with merits is a weak opener. Leading with character grounds is standard practice.

### Conditional Sections
- `chargesheet_status` — if chargesheet filed, cite S.173 CrPC compliance
- `default_bail` — if chargesheet not filed within 60/90 days, default bail under S.167(2) CrPC

---

## Blueprint 4 — Writ Petition (Art. 226 HC)

**Court:** High Court  
**Governing law:** Constitution of India, Art. 226; Rules of the specific HC

### Required Sections (strictly ordered — HC filing convention)

| # | Section ID | Content | Mandatory |
|---|-----------|---------|-----------|
| 1 | `court_header` | High Court name + jurisdiction | Yes |
| 2 | `writ_petition_no` | "WRIT PETITION (C/CRL/TAX) NO. ___ OF ____" | Yes |
| 3 | `cause_title` | Petitioner/s ... Petitioner vs Respondent/s ... Respondent | Yes |
| 4 | `synopsis` | 1-page summary of the case and the constitutional question | Yes |
| 5 | `list_of_dates` | Chronological table of key events, one line per date | Yes |
| 6 | `questions_of_law` | Precise constitutional/legal questions for the court | Yes |
| 7 | `facts` | Numbered body paragraphs — detailed narrative | Yes |
| 8 | `grounds` | Lettered grounds challenging the impugned order/action | Yes |
| 9 | `prayer` | Specific writs sought (mandamus/certiorari/prohibition/quo warranto) | Yes |
| 10 | `affidavit` | Verification affidavit, often a full supporting affidavit | Yes |

### Critical Ordering Rule
Synopsis and List of Dates are unique to HC filings. They are the first thing a bench reads. Lower court documents (JMFC, district civil court) do NOT have synopsis or list of dates. This is a hard format difference between HC and district court documents.

### Conditional Sections
- `alternative_remedy_para` — if tribunal/appellate remedy exists, must explain why writ is maintainable despite it
- `interim_relief_para` — if seeking stay, must separately set up the three-pronged test (prima facie, balance of convenience, irreparable harm)

---

## Blueprint 5 — Civil Plaint (CPC O.VII)

**Court:** Civil court at appropriate pecuniary level  
**Governing law:** CPC 1908, O.VII; Limitation Act 1963; Court Fees Act

### Required Sections

| # | Section ID | Content | Mandatory |
|---|-----------|---------|-----------|
| 1 | `court_header` | Court name | Yes |
| 2 | `suit_type` | "SUIT FOR RECOVERY / PERMANENT INJUNCTION / SPECIFIC PERFORMANCE / ..." | Yes |
| 3 | `cause_title` | Plaintiff v. Defendant | Yes |
| 4 | `plaint_header` | "PLAINT" | Yes |
| 5 | `facts` | Numbered paragraphs — all material facts | Yes |
| 6 | `cause_of_action` | Date + place where right of action arose | Yes |
| 7 | `jurisdiction_territorial` | Where defendant resides or cause of action arose | Yes |
| 8 | `jurisdiction_pecuniary` | Valuation of suit — must match court fee | Yes |
| 9 | `jurisdiction_subject_matter` | Why this court has subject-matter jurisdiction | Yes |
| 10 | `limitation` | When limitation period begins, which Article of Schedule I, Limitation Act | Yes |
| 11 | `valuation_court_fee` | Amount of suit + court fee computed and paid | Yes |
| 12 | `prayer` | Specific reliefs — no catch-all "any other relief" without primary relief | Yes |
| 13 | `verification` | Plaintiff's verification | Yes |

### Critical Ordering Rule
All three jurisdiction heads (territorial, pecuniary, subject matter) must appear. Missing any one is a standard preliminary objection raised by defence counsel. Valuation must appear before prayer — the court fee computation depends on the relief sought.

### Dependencies
- `court_fee_amount` = computed from relief valuation using applicable Court Fees Act schedule
- `limitation_article` = specific Article in Schedule I, Limitation Act 1963 (must be cited by article number, not just "within time")

---

## Common Elements Across All Blueprints

### Verification Clause
Present in every Indian court document. Standard form:
```
VERIFICATION
I, [full name], [occupation], [address], do hereby solemnly affirm and
verify that the contents of this [complaint/plaint/petition] are true
and correct to the best of my knowledge and belief and nothing material
has been concealed therefrom.

Verified at [place] on this [date].

[Signature]
Deponent
```

### Prayer Structure
- Always labeled as "PRAYER" or "RELIEF SOUGHT" in bold
- Numbered or lettered clauses: (a), (b), (c) or (i), (ii), (iii)
- Ends with: "And/or pass any other order(s) as this Hon'ble Court may deem fit in the interest of justice."
- Last clause is always costs

### What Changes Across Courts
The content of each section is universal. The format packaging changes:
- Court header format (see `formatting_engine.md`)
- Party label terminology (Complainant/Accused vs Petitioner/Respondent vs Plaintiff/Defendant)
- Exhibit label format (EX-CW1/A vs Annexure P-1 vs Ex.P-1)
- Whether Synopsis and List of Dates are required (HC only)
- Whether affidavit is standalone or in-text
- Vakalatnama form (court-specific prescribed form)
