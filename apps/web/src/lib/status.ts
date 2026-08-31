import type { IngestionStatus } from './api/types';
import { TERMINAL_STATUSES } from './api/types';

/**
 * Describing where a document has got to.
 *
 * Every status has words.
 * "processing" covers four distinct stages a user may need to tell apart
 * when something is slow.
 */

export interface StatusDescription {
	label: string;
	detail: string;
	/** Whether to keep polling. */
	pending: boolean;
	tone: 'pending' | 'ready' | 'problem';
}

const DESCRIPTIONS: Record<IngestionStatus, StatusDescription> = {
	queued: { label: 'Queued', detail: 'Waiting for a worker.', pending: true, tone: 'pending' },
	parsing: { label: 'Reading', detail: 'Extracting text.', pending: true, tone: 'pending' },
	chunking: {
		label: 'Read',
		detail: 'Waiting to be embedded.',
		pending: true,
		tone: 'pending',
	},
	embedding: {
		label: 'Embedding',
		detail: 'Turning passages into vectors.',
		pending: true,
		tone: 'pending',
	},
	indexing: { label: 'Indexing', detail: 'Checking the index.', pending: true, tone: 'pending' },
	ready: { label: 'Ready', detail: 'Searchable.', pending: false, tone: 'ready' },
	failed: {
		label: 'Failed',
		detail: 'Something went wrong. Try reindexing.',
		pending: false,
		tone: 'problem',
	},
	unsupported: {
		label: 'Unreadable',
		detail: 'No text could be found in this file.',
		pending: false,
		tone: 'problem',
	},
	cancelled: { label: 'Cancelled', detail: 'Superseded.', pending: false, tone: 'problem' },
	deleting: { label: 'Deleting', detail: 'Removing passages.', pending: true, tone: 'pending' },
	deleted: { label: 'Deleted', detail: 'Removed.', pending: false, tone: 'problem' },
};

export function describeStatus(status: IngestionStatus, detail?: string | null): StatusDescription {
	const described = DESCRIPTIONS[status];
	// The server's detail is more specific than ours whenever it sends one:
	// "no text layer, and OCR is off" beats "no text could be found".
	return detail ? { ...described, detail } : described;
}

export function isTerminal(status: IngestionStatus): boolean {
	return TERMINAL_STATUSES.includes(status);
}

/**
 * How long to wait before asking again.
 *
 * Backs off so a document that takes ten minutes does not cost six hundred
 * requests, and caps so a finished document is noticed promptly.
 */
export function pollDelayMs(attempt: number): number {
	return Math.min(1000 * 2 ** attempt, 15000);
}
