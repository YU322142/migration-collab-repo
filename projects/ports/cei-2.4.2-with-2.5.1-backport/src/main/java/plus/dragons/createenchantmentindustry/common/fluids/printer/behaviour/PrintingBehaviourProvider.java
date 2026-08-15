/*
 * Copyright (C) 2025  DragonsPlus
 * SPDX-License-Identifier: LGPL-3.0-or-later
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

package plus.dragons.createenchantmentindustry.common.fluids.printer.behaviour;

import java.util.Objects;

/** A registered Printer behaviour provider and its lookup priority. */
public record PrintingBehaviourProvider(int priority, PrintingBehaviour.Provider provider) {
    /** Default addon priority, evaluated after CEI's built-in providers. */
    public static final int DEFAULT_PRIORITY = 0;

    /** Priority used by CEI's built-in providers. */
    public static final int BUILTIN_PRIORITY = 1000;

    public PrintingBehaviourProvider(PrintingBehaviour.Provider provider) {
        this(DEFAULT_PRIORITY, provider);
    }

    public PrintingBehaviourProvider {
        Objects.requireNonNull(provider, "provider");
    }
}
