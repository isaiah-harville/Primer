import { ApiError, asProblem } from './client';
import type { ChatModelList, ConversationSummary, MessageSummary, ProblemDetail } from './types';

/**
 * Talking to Chat.
 *
 * Separate from `PrimerApi` because it is a separate service with its own
 * address: Control owns libraries and documents, Chat owns conversations.
 * Folding both into one client would mean one base URL for two deployments
 * that scale, fail, and are upgraded independently.
 *
 * Only the parts that are not a stream. Asking a question goes through
 * `/chat/ask`, which pipes the response through rather than collecting it.
 */
export interface ChatApiOptions {
	fetch?: typeof globalThis.fetch;
	baseUrl?: string;
}

export class ChatApi {
	private readonly fetch: typeof globalThis.fetch;
	private readonly baseUrl: string;

	constructor(options: ChatApiOptions = {}) {
		this.fetch = options.fetch ?? globalThis.fetch;
		this.baseUrl = (options.baseUrl ?? '').replace(/\/$/, '');
	}

	private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
		const response = await this.fetch(`${this.baseUrl}${path}`, init);
		if (!response.ok) {
			let problem: ProblemDetail;
			try {
				// Read rather than cast, so a body that is not the contract's
				// shape cannot reach a user as "[object Object]".
				problem = asProblem(await response.json(), response.status);
			} catch {
				problem = {
					code: 'unexpected_response',
					title: 'Unexpected response',
					status: response.status,
					detail: `Chat replied with ${response.status}.`,
					request_id: null,
				};
			}
			throw new ApiError(problem);
		}
		if (response.status === 204) return undefined as T;
		return (await response.json()) as T;
	}

	/**
	 * What can answer a question, and whether anything can.
	 *
	 * The reachability of the inference endpoint travels with the list
	 * rather than being inferred from its emptiness: those are different
	 * facts with different fixes, and a caller that guessed would tell an
	 * operator to restart the wrong thing.
	 */
	models(): Promise<ChatModelList> {
		return this.request('/api/v1/models');
	}

	/** The caller's own conversations, most recently updated first. */
	conversations(): Promise<ConversationSummary[]> {
		return this.request('/api/v1/conversations');
	}

	messages(conversationId: string): Promise<MessageSummary[]> {
		return this.request(`/api/v1/conversations/${conversationId}/messages`);
	}

	deleteConversation(conversationId: string): Promise<void> {
		return this.request(`/api/v1/conversations/${conversationId}`, { method: 'DELETE' });
	}
}
