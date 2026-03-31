/**
 * Document editor: shared constants (PDF field labels, tool configs, layout).
 */

/** PDF magic bytes for header check (%PDF-) */
export const PDF_HEADER_BYTES = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d]);

export const DEFAULT_PDF_WIDTH_PT = 612;
export const DEFAULT_PDF_HEIGHT_PT = 792;
export const PDF_TEXT_MARGIN = 50;
export const PDF_BOX_CLAMP_PAD = 4;
export const PDF_BOX_CLAMP_RIGHT = 20;
export const PREVIEW_DEBOUNCE_MS = 750;
export const DEFAULT_BOX_W = 200;
export const DEFAULT_BOX_H = 40;

export const PDF_FIELD_LABELS = {
  companyname: 'Company Name',
  company_name: 'Company Name',
  offerorname: 'Offeror Name',
  offeror_name: 'Offeror Name',
  contractoraddress: 'Contractor Address',
  contractor_address: 'Contractor Address',
  paymentbyaddress: 'Payment By Address',
  contractorcode: 'Contractor Code',
  contractor_code: 'Contractor Code',
  cage: 'CAGE',
  uei: 'UEI',
  tin: 'TIN',
  signername: 'Signer Name',
  signer_name: 'Signer Name',
  signertitle: 'Signer Title',
  authorizedname: 'Authorized Name',
  authorized_name: 'Authorized Name',
  authorizedtitle: 'Authorized Title',
  authorizedaddress: 'Authorized Address',
  authorized_address: 'Authorized Address',
  authorizedemail: 'Authorized Email',
  authorized_email: 'Authorized Email',
  contractofficername: 'Contract Officer Name',
  contract_officer_name: 'Contract Officer Name',
  contractorphone: 'Contractor Phone',
  contractor_phone: 'Contractor Phone',
  offerorphone: 'Offeror Phone',
  phone: 'Phone',
  phonenumber: 'Phone Number',
  telephone: 'Telephone',
  email: 'Email',
  signature: 'Signature',
  signaturefield: 'Signature',
  datesigned: 'Date Signed',
  date_signed: 'Date Signed',
  signaturedate: 'Signature Date',
  solicitationnumber: 'Solicitation Number',
  solicitation_number: 'Solicitation Number',
  noticeid: 'Notice ID',
  issuedate: 'Issue Date',
  issue_date: 'Issue Date',
  offerduedate: 'Offer Due Date',
  offer_due_date: 'Offer Due Date',
  duedate: 'Due Date',
  localtime: 'Local Time',
  contactname: 'Contact Name',
  contact_name: 'Contact Name',
  contactphone: 'Contact Phone',
  contact_phone: 'Contact Phone',
  contactemail: 'Contact Email',
  contact_email: 'Contact Email',
  deliverto: 'Deliver To',
  deliver_to: 'Deliver To',
  issuedby: 'Issued By',
  issuingoffice: 'Issuing Office',
  reqnumber: 'Req Number',
  pagenumber: 'Page Number',
  contractno: 'Contract No',
  ordernumber: 'Order Number',
  issuedbycode: 'Issued By Code',
  setasidepercent: 'Set-Aside %',
  discountterms: 'Discount Terms',
  rating: 'Rating',
  administeredbycode: 'Administered By Code',
  administeredby: 'Administered By',
  itemnum1: 'Item #',
  schedule1: 'Schedule',
  quantity1: 'Qty',
  unit1: 'Unit',
  unitprice1: 'Unit Price',
  amount1: 'Amount',
  accountingdata: 'Accounting Data',
  numberofcopies: 'Number of Copies',
  offerreference: 'Offer Reference',
  exceptions: 'Exceptions',
  contractingofficer: 'Contracting Officer',
  totalaward: 'Total Award',
  naics: 'NAICS',
  sizestandards: 'Size Standards',
  authorizedphone: 'Authorized Phone',
  receivedby: 'Received By',
  receivedatlocation: 'Received At Location',
  totalcontainers: 'Total Containers',
  shipnumber: 'Ship Number',
  vouchernumber: 'Voucher Number',
  amountverified: 'Amount Verified',
  checknumber: 'Check Number',
};

export const PDF_FIELD_BASE_LABELS = {
  itemnum: 'Item #',
  schedule: 'Schedule',
  quantity: 'Qty',
  unit: 'Unit',
  unitprice: 'Unit price',
  amount: 'Amount',
  date: 'Date',
  textfield: 'Text',
  checkbox: 'Check',
  signaturefield: 'Signature',
};

export const TEXT_BOX_COLORS = [
  '#000000', '#ffffff', '#dc2626', '#2563eb', '#16a34a', '#ca8a04', '#7c3aed', '#0d9488',
  '#6b7280', '#b91c1c', '#1d4ed8', '#15803d', '#a16207', '#6d28d9', '#0f766e',
];

export const TEXT_SUB_TOOLS = [
  { id: 'text', symbol: 'A', label: 'Text', cursor: 'text', title: 'Type text' },
  { id: 'cross', symbol: '✗', label: 'Cross', cursor: 'crosshair', title: 'X mark' },
  { id: 'check', symbol: '✓', label: 'Check', cursor: 'crosshair', title: 'Checkmark' },
  { id: 'dot', symbol: '•', label: 'Dot', cursor: 'crosshair', title: 'Dot' },
  { id: 'circle-around', symbol: '○', label: 'Circle around', cursor: 'crosshair', title: 'Circle around' },
  { id: 'crossout', symbol: 'S̶', label: 'Crossout', cursor: 'crosshair', title: 'Crossout' },
];

export const HIGHLIGHT_SUB_TOOLS = [
  { id: 'highlight', symbol: '🖍', label: 'Highlight', cursor: 'crosshair', title: 'Highlight' },
];

export const DRAW_SUB_TOOLS = [
  { id: 'pen', symbol: '∿', label: 'Draw', cursor: 'crosshair', title: 'Free flow pen' },
  { id: 'line', symbol: '—', label: 'Line', cursor: 'crosshair', title: 'Line' },
  { id: 'arrow', symbol: '→', label: 'Arrow', cursor: 'crosshair', title: 'Arrow' },
  { id: 'rectangle', symbol: '▭', label: 'Rectangle', cursor: 'crosshair', title: 'Rectangle' },
  { id: 'circle', symbol: '○', label: 'Circle', cursor: 'crosshair', title: 'Circle' },
  { id: 'polygon', symbol: '⬡', label: 'Polygon', cursor: 'crosshair', title: 'Polygon' },
  { id: 'stamp', symbol: '◉', label: 'Stamp', cursor: 'crosshair', title: 'Place custom stamp from palette' },
];

export const DRAW_SHAPE_SUBTOOLS = ['line', 'arrow', 'rectangle', 'circle', 'polygon'];
export const DRAW_HIT_PADDING = 20;
export const SIGNATURE_BOX_W = 140;
export const SIGNATURE_BOX_H = 50;
export const SIGNATURE_SIZE_MIN_W = 40;
export const SIGNATURE_SIZE_MAX_W = 400;
export const SIGNATURE_SIZE_MIN_H = 20;
export const SIGNATURE_SIZE_MAX_H = 200;
export const CROSSOUT_BOX_W = 56;
export const CROSSOUT_BOX_H = 8;
export const DRAW_PEN_COLOR = '#000000';
