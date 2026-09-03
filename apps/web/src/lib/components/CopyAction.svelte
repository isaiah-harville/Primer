<script lang="ts">
	import { Check, Copy } from '@lucide/svelte';
	import { Button } from '@sivir-ui/svelte';

	interface Props {
		/** What lands on the clipboard. */
		text: string;
		/** What the button says, and what it is called to a screen reader. */
		label: string;
	}

	let { text, label }: Props = $props();

	let copied = $state(false);
	let timer: ReturnType<typeof setTimeout> | undefined;

	/**
	 * Copy, and say so.
	 *
	 * The kit's own copy button renders an icon and nothing else - it takes a
	 * label for its tooltip but drops any children - so two of them side by
	 * side are two identical glyphs, and which one copies the citations is
	 * something you can only find out by trying it. This row is otherwise
	 * text buttons, so these are too.
	 */
	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
		} catch {
			// Clipboard access is refused outside a secure context, which a
			// self-hosted deployment reached over plain HTTP is. Falling back
			// keeps the button working there rather than failing silently.
			const staging = document.createElement('textarea');
			staging.value = text;
			staging.setAttribute('readonly', '');
			staging.style.position = 'fixed';
			staging.style.opacity = '0';
			document.body.append(staging);
			staging.select();
			document.execCommand('copy');
			staging.remove();
		}
		copied = true;
		clearTimeout(timer);
		timer = setTimeout(() => (copied = false), 2000);
	}
</script>

<Button variant="ghost" size="sm" onclick={copy} aria-label={copied ? `${label}: copied` : label}>
	{#if copied}
		<Check size={14} class="text-[var(--color-success)]" aria-hidden="true" />
	{:else}
		<Copy size={14} aria-hidden="true" />
	{/if}
	<!--
	  The label stays put while the icon changes. Swapping the words too
	  makes the row reflow under the pointer, so the next button moves out
	  from under a second click.
	-->
	{label}
</Button>
