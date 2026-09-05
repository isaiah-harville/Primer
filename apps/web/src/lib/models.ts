import type { ChatModel } from '$lib/api/types';

/**
 * Naming a model the way a request has to name it.
 *
 * A deployment can hold several providers and model names are not unique
 * across them - two endpoints serving `llama3.1:8b` is the ordinary case, not
 * a corner one - so a picker whose values were bare model names could not say
 * which endpoint a question should go to. The pair is the name.
 */
export function qualify(
	model: { id: string; provider_id?: string | null } | undefined | null,
): string {
	if (!model?.id) return '';
	return model.provider_id ? `${model.provider_id}:${model.id}` : model.id;
}

/**
 * The picker's value for the model a stored answer was written by.
 *
 * A conversation reopened has to come back on the model that answered it,
 * or a follow-up silently goes somewhere else. The pair is what makes that
 * possible: the name alone cannot say which endpoint, and picking the first
 * provider serving it would send the next question to a different machine
 * than the previous one.
 *
 * Empty when nothing was recorded - an answer from before the model was
 * kept, or one that failed before a model was chosen - which leaves the
 * picker on whatever the deployment offers by default.
 */
export function modelOf(
	messages: readonly { role: string; provider_model?: string | null; provider_id?: string | null }[],
): string {
	// The last answer, not the first: the model in force is the one that
	// wrote most recently, which is what a follow-up continues from.
	for (let index = messages.length - 1; index >= 0; index -= 1) {
		const message = messages[index];
		if (message.role !== 'assistant' || !message.provider_model) continue;
		return qualify({ id: message.provider_model, provider_id: message.provider_id });
	}
	return '';
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
