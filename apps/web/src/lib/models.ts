import type { ChatModel } from '$lib/api/types';

/**
 * Naming a model the way a request has to name it.
 *
 * A deployment can hold several providers and model names are not unique
 * across them - two endpoints serving `llama3.1:8b` is the ordinary case, not
 * a corner one - so a picker whose values were bare model names could not say
 * which endpoint a question should go to. The pair is the name.
 */
export function qualify(model: ChatModel | undefined): string {
	if (!model) return '';
	return model.provider_id ? `${model.provider_id}:${model.id}` : model.id;
}

/** Split a qualified name back into what the request sends. */
export function unqualify(value: string): { model?: string; provider_id?: string } {
	if (!value) return {};
	const separator = value.indexOf(':');
	// A bare name is still valid: a deployment with only its own provider
	// never qualifies anything, and an older client may not either.
	if (separator === -1) return { model: value };
	return {
		provider_id: value.slice(0, separator),
		model: value.slice(separator + 1),
	};
}
