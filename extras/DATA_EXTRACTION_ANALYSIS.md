# Data Extraction Analysis - Patterns and Strategies

## Overview
This document analyzes debug extracts to identify patterns for extracting:
1. **Deadline Extraction** (submission due date, time, timezone)
2. **Product/Service Details** (CLIN Analysis - manufacturer, part/model numbers, scope of work, timeline)
3. **Delivery Requirements** (complete address, special instructions, required delivery date)

---

## 1. Deadline Extraction Patterns

### Found Patterns:

#### Pattern 1: SF1449 Form Format
```
8. OFFER DUE DATE/LOCAL TIME
02/02/2026
```
- **Location**: Standard Form 1449, Block 8
- **Format**: Date only, sometimes with time
- **Keywords**: "OFFER DUE DATE", "LOCAL TIME", "DUE DATE"

#### Pattern 2: Amendment Extensions
```
The due date for the quotes has been extended to 02/02/2026.
```
- **Location**: Amendment documents (SF30)
- **Format**: Natural language with date
- **Keywords**: "extended to", "due date", "deadline"

#### Pattern 3: Solicitation Text
```
Quotes are due by the date and time listed in the PIEE solicitation module
```
- **Location**: Main solicitation text
- **Format**: Natural language
- **Keywords**: "due by", "deadline", "submission deadline"

#### Pattern 4: With Timezone
```
2026-01-21 07:00:52 (EST)
```
- **Location**: Combined synopsis/solicitation headers
- **Format**: ISO-like with timezone abbreviation
- **Keywords**: Timezone abbreviations (EST, EDT, CST, CDT, MST, MDT, PST, PDT, UTC)

### Current Implementation:
- Uses regex patterns with keywords: `deadline`, `due date`, `submission`, `offer due`, `quote due`
- Extracts dates using `dateutil.parser`
- Looks for time patterns: `\d{1,2}:\d{2}\s*(?:AM|PM)`
- Extracts timezone: `(EST|EDT|CST|CDT|MST|MDT|PST|PDT|UTC)`

### Recommended Enhancements:
1. **LLM-based extraction** for natural language deadlines
2. **Form field detection** for SF1449 Block 8
3. **Amendment tracking** to update deadlines when amendments extend dates
4. **Multiple deadline types**: submission, questions_due, delivery_deadline

---

## 2. Product/Service Details (CLIN Analysis)

### Found Patterns:

#### Pattern 1: Brand Name or Equal Format
```
Item: RTVX2C
Brand Name: Kubota
Part Number: RTVX2C
001 Salient Characteristics: Kubota RTV Full enclosed cab X1100C Diesel...
```
- **Location**: RFQ/RFP documents
- **Contains**: Brand name, part number, model number, salient characteristics
- **Keywords**: "Brand Name", "Part Number", "Model Number", "Salient Characteristics"

#### Pattern 2: Q&A Documents
```
Could you please provide the manufacturer's name and model number, if available?
| This is a custom cart per specifications in the drawing package
```
- **Location**: Q&A attachments
- **Contains**: Manufacturer info, custom vs. standard products
- **Keywords**: "manufacturer", "model number", "part number"

#### Pattern 3: Drawing References
```
Drawing 55222AD REV E
P/N 50032173 by Leuze Electronics
```
- **Location**: Technical drawings, specifications
- **Contains**: Drawing numbers, part numbers, manufacturer references
- **Keywords**: "Drawing", "P/N", "Part Number", "by [Manufacturer]"

#### Pattern 4: Scope of Work/Timeline
```
Delivery of two (2) carts are required within sixty (60) days after receipt of contract award
for a two (2) week initial testing and acceptance.
```
- **Location**: Statement of Work (SOW)
- **Contains**: Delivery timeline, testing requirements, acceptance criteria
- **Keywords**: "required within", "days after", "testing", "acceptance"

#### Pattern 5: Service Requirements
```
The Contractor shall provide the BEP with finished carts for use in the internal production process.
Upon completion of Offset and Intaglio print phase, carts will be used to hold sheets for no less than
seventy-two (72) hours of drying time.
```
- **Location**: SOW, technical requirements
- **Contains**: Service scope, performance requirements, usage specifications
- **Keywords**: "shall provide", "shall be used", "requirements", "specifications"

### Current CLIN Extraction:
- Extracts: `item_number`, `description`, `quantity`, `unit`, `base_item_number`, `contract_type`, `extended_price`
- **Missing**: `manufacturer`, `part_number`, `model_number`, `product_name` (partially extracted but not consistently)

### Recommended Enhancements:
1. **Enhanced CLIN schema** to include:
   - `manufacturer_name` (from "Brand Name", "by [Company]", Q&A responses)
   - `part_number` (from "Part Number", "P/N", drawing BOMs)
   - `model_number` (from "Model Number", product descriptions)
   - `drawing_number` (from "Drawing 55222AD", technical references)
   - `scope_of_work` (from SOW sections)
   - `delivery_timeline` (from "required within X days", delivery schedules)
   - `testing_requirements` (from acceptance/testing sections)

2. **LLM prompt enhancement** to specifically look for:
   - Brand name or equal sections
   - Drawing references and BOMs
   - Q&A responses about manufacturer/model
   - SOW sections with service requirements

---

## 3. Delivery Requirements

### Found Patterns:

#### Pattern 1: Complete Delivery Address
```
A. Place of Delivery: Fort Worth, T.X. Facility (WCF)
9000 Blue Mound Road | Fort Worth, T.X. 76131
```
- **Location**: SOW Section VII (Performance/Delivery Period)
- **Format**: Facility name, street address, city, state, ZIP
- **Keywords**: "Place of Delivery", "Deliver To", "Delivery Address", "FOB destination"

#### Pattern 2: FOB Terms
```
F.O.B. destination, offers submitted on a basis other than F.O.B. destination will be rejected
```
- **Location**: CLIN descriptions, solicitation terms
- **Format**: "F.O.B. destination" or "F.O.B. origin"
- **Keywords**: "F.O.B.", "FOB", "destination", "origin"

#### Pattern 3: Special Delivery Instructions
```
Delivery of two (2) carts are required within sixty (60) days after receipt of contract award
for a two (2) week initial testing and acceptance. After testing is completed, the carts will
follow a staggered delivery schedule, that must be agreed upon by contractor and COR.
```
- **Location**: SOW delivery sections
- **Contains**: Timeline, testing requirements, staggered schedules
- **Keywords**: "required within", "days after", "staggered delivery", "delivery schedule"

#### Pattern 4: Delivery Date Requirements
```
Preferred Delivery Time: Within 30 days (please specify the exact delivery time in your quote)
```
- **Location**: CLIN descriptions, solicitation terms
- **Format**: Timeframe or specific date
- **Keywords**: "Preferred Delivery Time", "Delivery Date", "Required Delivery", "Delivery Deadline"

#### Pattern 5: Shipping/Packing Instructions
```
Please advise on the preferred packing method for the carts: one per box or bulk packed on skids.
| Skids or most efficient method for packing/delivery.
```
- **Location**: Q&A documents, SOW
- **Contains**: Packing requirements, shipping methods
- **Keywords**: "packing method", "shipping", "delivery method"

#### Pattern 6: Dock/Facility Requirements
```
For the 5 semi-trailer loads anticipated for the full delivery, are there specific height or dock
requirements at the Fort Worth Currency Facility (WCF) that would preclude the use of standard
53-foot dry vans or flatbeds? | No
```
- **Location**: Q&A documents
- **Contains**: Facility constraints, shipping vehicle requirements
- **Keywords**: "dock requirements", "facility", "height", "semi-trailer"

### Current Implementation:
- **Not currently extracted** as structured data
- Delivery address may be mentioned in document text but not parsed

### Recommended Enhancements:
1. **New extraction schema** for delivery requirements:
   ```python
   {
       "delivery_address": {
           "facility_name": "Fort Worth Currency Facility (WCF)",
           "street_address": "9000 Blue Mound Road",
           "city": "Fort Worth",
           "state": "TX",
           "zip_code": "76131",
           "country": "US"
       },
       "fob_terms": "destination",  # or "origin"
       "delivery_timeline": "60 days after contract award",
       "delivery_date": None,  # specific date if provided
       "special_instructions": [
           "Initial 2 carts for testing within 60 days",
           "Staggered delivery schedule after testing",
           "Skids or most efficient packing method"
       ],
       "packing_requirements": "Skids or most efficient method",
       "facility_constraints": {
           "dock_requirements": None,
           "height_restrictions": None,
           "vehicle_restrictions": None
       }
   }
   ```

2. **LLM-based extraction** with prompt:
   - Look for "Place of Delivery", "Deliver To" sections
   - Extract complete addresses (street, city, state, ZIP)
   - Identify FOB terms
   - Extract delivery timelines and schedules
   - Capture special instructions and packing requirements

---

## General Extraction Strategy

### Approach 1: Regex + Pattern Matching (Current)
- **Pros**: Fast, deterministic
- **Cons**: Misses natural language, requires many patterns
- **Use for**: Structured forms (SF1449, SF30), standardized fields

### Approach 2: LLM-based Extraction (Recommended)
- **Pros**: Handles natural language, flexible, comprehensive
- **Cons**: API costs, slower, may need validation
- **Use for**: SOW sections, Q&A documents, amendments, unstructured text

### Approach 3: Hybrid (Best)
1. **First pass**: Regex for structured forms (SF1449 Block 8, delivery address patterns)
2. **Second pass**: LLM for natural language sections (SOW, Q&A, amendments)
3. **Validation**: Cross-reference multiple sources, prioritize structured data

---

## Implementation Recommendations

### 1. Enhanced Deadline Extraction
- Add LLM prompt to extract deadlines from natural language
- Track deadline changes in amendments
- Extract multiple deadline types (submission, questions, delivery)

### 2. Enhanced CLIN Extraction
- Update CLIN schema to include manufacturer, part/model numbers
- Enhance LLM prompt to look for brand name or equal sections
- Extract drawing references and BOM information
- Extract scope of work and service requirements

### 3. New Delivery Requirements Extraction
- Create new extraction module for delivery information
- Use LLM to extract from SOW sections
- Parse addresses using structured patterns + LLM validation
- Extract FOB terms, timelines, and special instructions

### 4. Cross-Document Correlation
- Link CLINs with delivery requirements
- Correlate deadlines across documents (base + amendments)
- Merge manufacturer info from multiple sources (CLINs, Q&A, drawings)

---

## Example Extraction Targets

### From Opportunity 145 (Stack and Rack Carts):

**Deadlines:**
- Submission: `02/02/2026` (from SF1449 Block 8)
- Extended from original date (from Amendment)

**CLIN Details:**
- Item: `0001`
- Description: `Stack and Rack Carts...`
- Quantity: `250 Each`
- Manufacturer: `Custom per specifications` (from Q&A)
- Drawing: `55222AD REV E` (from technical drawings)
- Part Numbers: `55222BF`, `55222BP`, `55222BR`, etc. (from BOM)

**Delivery Requirements:**
- Address: `Fort Worth, TX Facility (WCF), 9000 Blue Mound Road, Fort Worth, TX 76131`
- Timeline: `2 carts within 60 days for testing, then staggered delivery`
- FOB: `Destination` (implied from "FOB destination" patterns)
- Packing: `Skids or most efficient method`

### From Opportunity 147 (Kubota RTV):

**CLIN Details:**
- Brand Name: `Kubota`
- Part Number: `RTVX2C`
- Model: `X1100C Diesel`
- Description: `Full enclosed cab, turn signals, work lights, turf tires`

**Delivery Requirements:**
- Preferred Delivery: `Within 30 days`
- FOB: `Destination`

---

## Next Steps

1. **Create enhanced extraction prompts** for LLM-based extraction
2. **Update CLIN schema** to include manufacturer, part/model numbers
3. **Create delivery requirements extraction module**
4. **Implement hybrid extraction** (regex + LLM)
5. **Add cross-document correlation** logic
