<script lang="ts">
	import { Cpu } from '@lucide/svelte';
	import { DropdownMenu } from '@sivir-ui/svelte';

	interface Props {
		models: { id: string; default: boolean }[];
		/** Empty means the deployment's default. */
		value?: string;
		//: True when Chat could not be reached for the list, as opposed to a
		//: deployment that was reached and genuinely offers only one model.
		//: The two look identical in `models` alone - both empty or
		//: single-entry - so the caller has to say which one this is.
		unavailable?: boolean;
	}

	let { models, value = $bindable(''), unavailable = false }: Props = $props();

	let chosen = $derived(models.find((model) => model.id === value));
	let fallback = $derived(models.find((model) => model.default) ?? models[0]);
	let shown = $derived(chosen ?? fallback);
</script>

<!--
  Hidden entirely when there is nothing to choose between and nothing wrong:
  a picker with one option is a control that does nothing, and most
  deployments serve one model. Shown anyway when the list could not be
  fetched, because that state should not look identical to the deployment
  simply having one model - a person watching it happen needs to see
  something, not nothing.
-->
{#if models.length > 1 || unavailable}
	<DropdownMenu.Root>
		<DropdownMenu.Trigger
			variant="ghost"
			size="sm"
			class={unavailable ? 'text-error' : 'text-muted-foreground'}
		>
			<Cpu size={14} aria-hidden="true" />
			<span class="max-w-[12rem] truncate" title={shown?.id}>
				{shown?.id ?? (unavailable ? 'Model unavailable' : 'Default')}
			</span>
		</DropdownMenu.Trigger>
		<DropdownMenu.Content>
			{#if models.length === 0}
				<p class="max-w-56 px-2.5 py-2 text-xs text-muted-foreground">
					Could not reach the model list. Questions will still be answered by this
					deployment's default model.
				</p>
			{:else}
				<DropdownMenu.RadioGroup {value} onValueChange={(next) => (value = next)}>
					{#each models as model (model.id)}
						<DropdownMenu.RadioItem value={model.id}>
							<span class="flex w-full items-center justify-between gap-4">
								<span class="truncate">{model.id}</span>
								{#if model.default}
									<span class="text-xs text-muted-foreground">Default</span>
								{/if}
							</span>
						</DropdownMenu.RadioItem>
					{/each}
				</DropdownMenu.RadioGroup>
			{/if}
		</DropdownMenu.Content>
	</DropdownMenu.Root>
{/if}
