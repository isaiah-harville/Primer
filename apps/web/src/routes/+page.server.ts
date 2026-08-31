import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = () => {
	// Everything in Primer hangs off a library, so that is the front door.
	redirect(307, '/libraries');
};
