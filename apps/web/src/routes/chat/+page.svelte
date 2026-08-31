<script lang="ts">
	import { Alert, Button, Card, Conversation, Markdown, Message, PromptComposer } from '@sivir-ui/svelte';
	import CitationPanel from '$lib/components/CitationPanel.svelte';
	import ResponseActions from '$lib/components/ResponseActions.svelte';
	import { emptyStream, parseEvents, reduce, type StreamState } from '$lib/api/sse';
	import type { MessageSummary } from '$lib/api/types';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	// Defaults to the first library, and follows it if the list loads later.
	let libraryId = $state('');
	$effect(() => {
		if (!libraryId && data.libraries.length > 0) libraryId = data.libraries[0].id;
	});
	let question = $state('');
	let turns = $state<{ question: string; stream: StreamState }[]>([]);
	let streaming = $state(false);
	let sourcesOpen = $state(false);
	let sourcesFor = $state<StreamState | null>(null);

	async function ask() {
		const asked = question.trim();
		if (!asked || !libraryId || streaming) return;

		question = '';
		streaming = true;
		const turn = { question: asked, stream: emptyStream() };
		turns = [...turns, turn];

		try {
			const response = await fetch('/chat/ask', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ library_id: libraryId, message: asked })
			});
			if (!response.body) throw new Error('The server sent no response body.');

			for await (const event of parseEvents(response.body)) {
				// Reassigning the array is what makes Svelte see the change;
				// the state object itself is replaced by the reducer.
				turn.stream = reduce(turn.stream, event);
				turns = [...turns];
			}
		} catch {
			turn.stream = {
				...turn.stream,
				error: { code: 'connection_lost', detail: 'The connection closed before the answer finished.' },
				done: true
			};
			turns = [...turns];
		} finally {
			streaming = false;
		}
	}

	function completed(stream: StreamState): MessageSummary | null {
		if (stream.message) return stream.message;
		// A failed stream still has an answer worth copying: the text it
		// managed to write before it stopped.
		if (!stream.error || !stream.messageId) return null;
		return {
			id: stream.messageId,
			conversation_id: stream.conversationId ?? '',
			role: 'assistant',
			state: 'failed',
			content: stream.text,
			citations: stream.citations,
			error_code: stream.error.code,
			created_at: new Date().toISOString()
		};
	}
</script>

<h1 class="text-2xl font-bold">Chat</h1>

{#if data.libraries.length === 0}
	<p class="mt-4 text-muted-foreground">
		Create a library and add some documents before asking a question.
	</p>
{:else}
	<Card.Root class="mt-4">
		<Card.Content>
			<label class="flex items-center gap-3 text-sm">
				<span class="font-medium">Library</span>
				<!--
				  A native select: it is one choice from a short list, and the
				  browser's own control is keyboard- and screen-reader-correct
				  everywhere without any work.
				-->
				<select
					bind:value={libraryId}
					class="rounded-md border border-border bg-background px-2 py-1.5"
				>
					{#each data.libraries as library (library.id)}
						<option value={library.id}>{library.name}</option>
					{/each}
				</select>
			</label>
		</Card.Content>
	</Card.Root>

	<Conversation.Root class="mt-6 min-h-[24rem]">
		<Conversation.Content>
			{#if turns.length === 0}
				<Conversation.Empty>
					Ask a question about this library. Every answer cites the passages it used.
				</Conversation.Empty>
			{/if}

			{#each turns as turn, index (index)}
				<Message.Root from="user">
					<Message.Content>{turn.question}</Message.Content>
				</Message.Root>

				<Message.Root from="assistant" status={turn.stream.done ? 'idle' : 'streaming'}>
					<Message.Content>
						<!--
						  Rendered as Markdown, since models write it. The text
						  is the model's, so it is rendered rather than
						  interpreted: nothing here acts on it.
						-->
						<Markdown content={turn.stream.text} />
					</Message.Content>

					{#if turn.stream.error}
						<Alert.Root variant="error" class="mt-2">
							<Alert.Description>
								{turn.stream.error.detail ?? 'The answer stopped before it finished.'}
							</Alert.Description>
						</Alert.Root>
					{/if}

					{#if turn.stream.done}
						{@const message = completed(turn.stream)}
						{#if message}
							<Message.Actions>
								<ResponseActions
									{message}
									onshowsources={() => {
										sourcesFor = turn.stream;
										sourcesOpen = true;
									}}
								/>
							</Message.Actions>
						{/if}
					{/if}
				</Message.Root>
			{/each}
		</Conversation.Content>
		<Conversation.ScrollButton />
	</Conversation.Root>

	<PromptComposer.Root
		bind:value={question}
		status={streaming ? 'submitting' : 'idle'}
		onSubmit={ask}
		class="mt-4"
	>
		<PromptComposer.Input placeholder="Ask about this library…" aria-label="Your question" />
		<PromptComposer.Toolbar>
			<PromptComposer.Actions>
				<PromptComposer.Submit />
			</PromptComposer.Actions>
		</PromptComposer.Toolbar>
	</PromptComposer.Root>

	{#if sourcesFor}
		<CitationPanel citations={sourcesFor.citations} bind:open={sourcesOpen} />
	{/if}
{/if}
