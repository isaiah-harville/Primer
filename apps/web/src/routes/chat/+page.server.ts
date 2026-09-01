import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

/**
 * Which models this deployment offers.
 *
 * From Chat rather than Control: the list is Chat's configuration, and
 * asking Control to relay it would give two services an opinion about one
 * setting.
 *
 * A failure here is not a failure of the page. Chat being unreachable is
 * already visible everywhere else, and an empty list simply means no picker
 * rather than a chat screen that will not load.
 */
export const load: PageServerLoad = async ({ request, fetch }) => {
	const headers = new Headers();
	for (const name of ['x-auth-request-user', 'x-auth-request-email', 'x-auth-request-groups']) {
		const value = request.headers.get(name);
		if (value) headers.set(name, value);
	}

	try {
		const response = await fetch(
			`${env.PRIMER_CHAT_URL ?? 'http://localhost:8100'}/api/v1/models`,
			{ headers },
		);
		if (!response.ok) return { models: [] };
		const body = (await response.json()) as { models?: { id: string; default: boolean }[] };
		return { models: body.models ?? [] };
	} catch {
		return { models: [] };
	}
};
