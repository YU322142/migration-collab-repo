package com.tom.storagemod.inventory.filter;

import java.util.ArrayList;
import java.util.List;

import com.tom.storagemod.inventory.StoredItemStack;
import com.tom.storagemod.util.Priority;

public interface IFilter {
	ItemPredicate getItemPred();
	boolean isKeepLast();
	Priority getPriority();

	/**
	 * Stable identity for an equivalent filter route. Most filters are persistent
	 * block attachments, so their object identity is already the correct key.
	 */
	default Object getRouteKey() {
		return this;
	}

	/** Monotonic revision for predicate/counting changes observed by trackers. */
	default long getRevision() {
		return 0L;
	}

	public static class MultiFilter implements IFilter, ItemPredicate {
		private List<IFilter> filters = new ArrayList<>();

		public MultiFilter(IFilter... filters) {
			for (IFilter f : filters) {
				if (f instanceof MultiFilter mf) {
					for (IFilter nf : mf.filters) {
						add(nf);
					}
				} else {
					add(f);
				}
			}
		}

		private void add(IFilter nf) {
			if (!filters.contains(nf)) {
				filters.add(nf);
			}
		}

		@Override
		public ItemPredicate getItemPred() {
			return this;
		}

		@Override
		public boolean isKeepLast() {
			for (IFilter f : filters) {
				if (f.isKeepLast())return true;
			}
			return false;
		}

		@Override
		public Priority getPriority() {
			int s = 0;
			for (IFilter f : filters) {
				s += f.getPriority().getSorting();
			}
			return Priority.fromSorting(s);
		}

		@Override
		public boolean test(StoredItemStack stack) {
			for (IFilter f : filters) {
				if(!f.getItemPred().test(stack))
					return false;
			}
			return true;
		}

		@Override
		public void updateState() {
			for (IFilter f : filters) {
				f.getItemPred().updateState();
			}
		}

		@Override
		public Object getRouteKey() {
			return new MultiFilterRouteKey(filters.stream().map(IFilter::getRouteKey).toList());
		}

		@Override
		public long getRevision() {
			long revision = 0L;
			for (IFilter filter : filters)revision += filter.getRevision();
			return revision;
		}

		private static record MultiFilterRouteKey(List<Object> filters) {}

		@Override
		public String toString() {
			return filters.toString();
		}
	}
}
