import type {
	DeploymentCapabilities,
	DocumentSummary,
	LibrarySummary,
	ProblemDetail,
} from './types';

/**
 * Talking to Primer.
 *
 * Every call goes through this server, never from the browser to Control
 * directly: the identity headers Primer trusts are injected by the proxy in
 * front of it, and a browser that could reach Control could set them itself.
 */

export class ApiError extends Error {
	readonly status: number;
	readonly code: string;
	readonly requestId: string | null;

	constructor(problem: ProblemDetail) {
		// The server's own words, which are already written for a user.
		// Inventing a friendlier message here would hide the detail that
		// says which of several similar failures this was.
		super(problem.detail ?? problem.title);
		this.name = 'ApiError';
		this.status = problem.status;
		this.code = problem.code;
		this.requestId = problem.request_id;
	}
}

export interface ApiOptions {
	fetch?: typeof globalThis.fetch;
	baseUrl?: string;
}

export class PrimerApi {
	private readonly fetch: typeof globalThis.fetch;
	private readonly baseUrl: string;

	constructor(options: ApiOptions = {}) {
		this.fetch = options.fetch ?? globalThis.fetch;
		this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
	}

	private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
		const response = await this.fetch(`${this.baseUrl}${path}`, init);
		if (!response.ok) {
			throw new ApiError(await this.problemFrom(response));
		}
		if (response.status === 204) {
			return undefined as T;
		}
		return (await response.json()) as T;
	}

	private async problemFrom(response: Response): Promise<ProblemDetail> {
		try {
			return (await response.json()) as ProblemDetail;
		} catch {
			// A proxy timeout or a crash produces a non-JSON body. Reporting
			// the status honestly beats a parse error the user cannot act on.
			return {
				code: 'unexpected_response',
				title: 'Unexpected response',
				status: response.status,
				detail: `The server replied with ${response.status}.`,
				request_id: null,
			};
		}
	}

	capabilities(): Promise<DeploymentCapabilities> {
		return this.request('/api/v1/capabilities');
	}

	libraries(): Promise<LibrarySummary[]> {
		return this.request('/api/v1/libraries');
	}

	createLibrary(name: string): Promise<LibrarySummary> {
		return this.request('/api/v1/libraries', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name }),
		});
	}

	/** Copy a library into a new one the caller owns. */
	duplicateLibrary(libraryId: string, name?: string): Promise<LibrarySummary> {
		return this.request(`/api/v1/libraries/${libraryId}/duplicate`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(name ? { name } : {}),
		});
	}

	deleteLibrary(libraryId: string): Promise<void> {
		return this.request(`/api/v1/libraries/${libraryId}`, { method: 'DELETE' });
	}

	documents(libraryId: string): Promise<DocumentSummary[]> {
		return this.request(`/api/v1/libraries/${libraryId}/documents`);
	}

	document(libraryId: string, documentId: string): Promise<DocumentSummary> {
		return this.request(`/api/v1/libraries/${libraryId}/documents/${documentId}`);
	}

	upload(libraryId: string, file: File): Promise<DocumentSummary> {
		const body = new FormData();
		body.append('file', file);
		// No Content-Type header: the browser sets it with the multipart
		// boundary, and overriding it produces an unparseable request.
		return this.request(`/api/v1/libraries/${libraryId}/documents`, { method: 'POST', body });
	}

	reindex(libraryId: string, documentId: string): Promise<DocumentSummary> {
		return this.request(`/api/v1/libraries/${libraryId}/documents/${documentId}/reindex`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: '{}',
		});
	}

	deleteDocument(libraryId: string, documentId: string): Promise<void> {
		return this.request(`/api/v1/libraries/${libraryId}/documents/${documentId}`, {
			method: 'DELETE',
		});
	}
}
