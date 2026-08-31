/**
 * The shapes Primer's HTTP API returns.
 *
 * Hand-written to mirror `primer_contracts`, and checked against the live
 * OpenAPI schema by a test rather than by hoping. A generated client would
 * be less work to keep in step, but generating one at build time makes the
 * front end unbuildable whenever the API is not running.
 */

export type IngestionStatus =
	| 'queued'
	| 'parsing'
	| 'chunking'
	| 'embedding'
	| 'indexing'
	| 'ready'
	| 'failed'
	| 'unsupported'
	| 'cancelled'
	| 'deleting'
	| 'deleted';

/** States where nothing further will happen without the user acting. */
export const TERMINAL_STATUSES: readonly IngestionStatus[] = [
	'ready',
	'failed',
	'unsupported',
	'cancelled',
	'deleted',
];

export interface LibrarySummary {
	id: string;
	name: string;
	owner_user_id: string;
	document_count: number;
	created_at: string;
	updated_at: string;
}

export interface DocumentSummary {
	id: string;
	library_id: string;
	current_version_id: string;
	filename: string;
	media_type: string;
	byte_size: number;
	status: IngestionStatus;
	status_detail: string | null;
	created_at: string;
	updated_at: string;
}

export interface DeploymentCapabilities {
	auth_enabled: boolean;
	ingestion_available: boolean;
	chat_available: boolean;
	tools_available: boolean;
	max_upload_bytes: number;
	supported_extensions: string[];
}

export interface SourceLocator {
	page: number | null;
	section: string | null;
}

export interface Citation {
	document_id: string;
	document_version_id: string;
	chunk_id: string;
	locator: SourceLocator | null;
	excerpt: string | null;
}

export interface MessageSummary {
	id: string;
	conversation_id: string;
	role: 'user' | 'assistant';
	state: 'streaming' | 'completed' | 'failed' | 'cancelled';
	content: string;
	citations: Citation[];
	error_code: string | null;
	created_at: string;
}

export interface ConversationSummary {
	id: string;
	library_id: string;
	owner_user_id: string;
	title: string;
	created_at: string;
	updated_at: string;
}

/** An RFC 9457 problem document. Every error from Primer has this shape. */
export interface ProblemDetail {
	code: string;
	title: string;
	status: number;
	detail: string | null;
	request_id: string | null;
}
