export interface Invoice {
  id: string;
  number: string;
  customer_id: string;
  customer_name: string;
  invoice_date: string;
  subtotal_paise: number;
  tax_paise: number;
  total_paise: number;
  allocated_paise: number;
  due_paise: number;
  status: string;
}

export interface Payment {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  amount_paise: number;
  state: string;
  mode: string;
  provider: string;
  method: string | null;
  received_at: string;
  provider_payment_id: string;
  payment_request_id: string | null;
  intended_invoice_id: string | null;
  evidence_type: string | null;
  note: string | null;
  allocated_paise: number;
  unallocated_paise: number;
}

export interface PaymentRequest {
  id: string;
  invoice_id: string;
  customer_id: string;
  amount_paise: number;
  status: string;
  provider: string | null;
  mode: string | null;
  link_url: string | null;
  created_at: string;
  customer_name?: string;
  invoice_number?: string;
}

export interface PromiseRow {
  id: string;
  customer_id: string;
  customer_name: string;
  invoice_id: string | null;
  amount_paise: number;
  promised_date: string;
  method: string;
  pickup_window: string | null;
  status: string;
  evidence_source: string;
  evidence_text: string;
  simulated: boolean;
}

export interface Customer {
  id: string;
  name: string;
  phone: string | null;
  preferred_method: string | null;
  preference_note: string | null;
  outstanding_paise: number;
  promised_open_paise: number;
  consents: Record<string, string | null>;
}

export interface Audit {
  id: string;
  actor: string;
  action: string;
  data: Record<string, unknown>;
  created_at: string;
}
