---
name: filing_checklist
description: Pre-filing checklist — court fee, process fee, vakalatnama, index of documents verification.
trigger_keywords:
  - checklist
  - filing checklist
  - what to file
  - documents required
  - court filing
  - file in court
  - procedural compliance
  - what do I need to file
  - how to file
  - next steps after draft
matter_types:
  - writ petition
  - plaint
  - injunction
  - bail application
  - written statement
  - legal notice
  - criminal revision
  - affidavit
---

# Filing Checklist — Indian Courts

You are LexAgent's procedural compliance module. When a draft is complete, use this skill to produce a court-specific filing checklist so the lawyer knows exactly what to attach and do before handing the matter to a filing clerk.

## How to Use This Skill

After producing a draft, append a **Filing Checklist** section at the bottom using the template below. Populate it based on the `matter_type`, `jurisdiction`, and `parties` in the current matter state.

---

## Checklist Template

### Pre-Filing Checklist — {matter_type} | {jurisdiction}

**Court copies required**
- [ ] Original signed set (court copy)
- [ ] File copy (for court's records)
- [ ] Served copy for each respondent/opposite party
- [ ] Lawyer's own copy

**Mandatory annexures**
- [ ] Vakalatnama (signed by client + advocate) — check court's prescribed form
- [ ] Court fee receipt / stamp paper (see `calculate_court_fee` output)
- [ ] Index of documents (cause title + list of annexures)
- [ ] Affidavit verifying the pleadings (Order VI Rule 15A CPC for civil matters)

**Identity & authority documents**
- [ ] Board resolution / authority letter (if filing on behalf of a company)
- [ ] Power of attorney (if instructing advocate who has not met the party)

**Matter-specific checklist items**

#### Writ Petition (Art. 226 / 32)
- [ ] Copy of the impugned order/notice being challenged
- [ ] Proof of exhaustion of alternative remedy (or affidavit explaining why not exhausted)
- [ ] Any correspondence with the respondent authority
- [ ] Previous orders (if any interim relief was granted earlier)

#### Plaint / Civil Suit
- [ ] All documentary evidence listed in the plaint
- [ ] Valuation certificate (for suits where ad valorem fee applies)
- [ ] Limitation affidavit (if cause of action is more than 2 years old)
- [ ] Copies of relevant agreements/contracts/invoices

#### Injunction Application (Order XXXIX CPC)
- [ ] Separate affidavit in support of the I.A.
- [ ] Evidence of prima facie case, balance of convenience, irreparable harm
- [ ] Proposed draft of the injunction order (for ex-parte applications)

#### Bail Application (Cr.P.C. 437 / 438 / 439)
- [ ] Copy of FIR
- [ ] Chargesheet (if filed)
- [ ] Remand orders / custody order
- [ ] Surety documents (residential proof, ID, bank statement of surety)
- [ ] Accused's personal background affidavit (domicile, employment, family)

#### Legal Notice
- [ ] Postal tracking receipt (registered post / speed post)
- [ ] Proof of delivery (acknowledgement card / tracking report)
- [ ] Copy of the notice sent (retain for future litigation)

#### Written Statement
- [ ] Copy of the plaint being responded to
- [ ] All documents supporting the defence
- [ ] Documents in support of any counterclaim (filed separately under Order VIII Rule 6A)

#### Affidavit
- [ ] Non-judicial stamp paper of appropriate denomination (state-specific)
- [ ] Notarisation / oath commissioner's signature and seal
- [ ] Exhibits referred to in the affidavit (marked as Exhibit A, B, etc.)

---

## Post-Filing Steps

1. **Get filing number** from the court registry and note it in matter MEMORY.md.
2. **Set a reminder** for the next hearing date using `/reminder <matter_id> <date>`.
3. **Serve copies** on all opposite parties before or at the time of first hearing.
4. **Update matter memory** with any conditions attached to filing or admission.
5. **Check for defects**: registries return filings for re-filing if court fee is wrong, copies are missing, or vakalatnama is unsigned. Return within the time given.

---

## Procedural Deadlines to Watch

| Document | Deadline |
|----------|---------|
| Written Statement | 30 days from service of summons (extendable to max 90 days, Order VIII Rule 1 CPC) |
| Bail Application — Chargesheet | File before 60 days (non-serious) / 90 days (serious) custody if no chargesheet filed (default bail S.167 CrPC) |
| First Appeal | 30 days from decree (Order XLII CPC); 90 days to High Court |
| Writ Petition (HC) | No fixed period — file within reasonable time (laches doctrine applies after ~3 years) |
| Consumer Complaint | 2 years from cause of action (S.69 Consumer Protection Act 2019) |
| Revision | 90 days from the impugned order (S.115 CPC; S.397 CrPC) |

---

*This checklist is a starting point. Always verify court-specific requirements with the registry before filing.*
