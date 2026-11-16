import presetData from "./presets.json" with { type: "json" };
import { normalizeCoreAttrs, normalizeMark, normalizeNode } from "./declarations.js";
import type { Attr, CoreAttrs, MarkSpec, NodeSpec } from "./declarations.js";
import { optionsObject, optionNames } from "./options.js";

type PresetData = Record<string, {
    marks?: MarkSpec[];
    nodes?: NodeSpec[];
    core_attrs?: CoreAttrs;
}>;

const data = presetData as PresetData;

function mark(name: string): MarkSpec {
    return normalizeMark(data[name].marks![0]);
}

function nodes(name: string): NodeSpec[] {
    return data[name].nodes!.map(normalizeNode);
}

function coreAttrs(name: string): CoreAttrs {
    return normalizeCoreAttrs(data[name].core_attrs!);
}

export type TextStyleOptions = {
    backgroundColor?: boolean;
    color?: boolean;
    fontFamily?: boolean;
    fontSize?: boolean;
    lineHeight?: boolean;
    mergeNestedSpanStyles?: boolean;
};

export function textStyle(settings: TextStyleOptions = {}): MarkSpec {
    const options = optionsObject(settings, "options");
    optionNames(options, ["backgroundColor", "color", "fontFamily", "fontSize", "lineHeight",
                          "mergeNestedSpanStyles"]);
    const {
        backgroundColor = true, color = true, fontFamily = true, fontSize = true, lineHeight = true,
        mergeNestedSpanStyles = true,
    } = options;
    const template = mark("TEXT_STYLE");
    const enabled = [backgroundColor, color, fontFamily, fontSize, lineHeight];
    return {
        ...template,
        attrs: Object.fromEntries(Object.entries(template.attrs!).filter((_, index) => enabled[index])
            .map(([name, attr]) => [name, { ...attr, inherit: mergeNestedSpanStyles } as Attr])),
    };
}

const alignTypes = coreAttrs("TEXT_ALIGN");
const alignAttrs = Object.values(alignTypes)[0];
const align = Object.values(alignAttrs)[0];

export type TextAlignOptions = {
    types?: readonly string[];
    alignments?: readonly string[];
    defaultAlignment?: string | null;
};

export function textAlign(settings: TextAlignOptions = {}): CoreAttrs {
    const options = optionsObject(settings, "options");
    optionNames(options, ["types", "alignments", "defaultAlignment"]);
    const {
        types = Object.keys(alignTypes), alignments = align.choices, defaultAlignment = align.default,
    } = options;
    return Object.fromEntries((types as readonly string[]).map((type) => [
        type,
        Object.fromEntries(Object.entries(alignAttrs).map(([name, attr]) => [
            name, { ...attr, choices: [...alignments as readonly string[]], default: defaultAlignment } as Attr,
        ])),
    ]));
}

const link = coreAttrs("LINK_ATTRS").link;

export type LinkAttrsOptions = {
    target?: string | null;
    rel?: string | null;
    class?: string | null;
};

export function linkAttrs(settings: LinkAttrsOptions = {}): CoreAttrs {
    const options = optionsObject(settings, "options");
    optionNames(options, ["target", "rel", "class"]);
    const { target = link.target.default, rel = link.rel.default, class: className = link.class.default } = options;
    const defaults = [target, rel, className];
    return {
        link: Object.fromEntries(Object.entries(link).map(([name, attr], index) => (
            [name, { ...attr, default: defaults[index] } as Attr]
        ))),
    };
}

export const UNDERLINE = mark("UNDERLINE");
export const HIGHLIGHT = mark("HIGHLIGHT");
export const SUBSCRIPT = mark("SUBSCRIPT");
export const SUPERSCRIPT = mark("SUPERSCRIPT");
export const TEXT_STYLE = textStyle();
export const MENTION = nodes("MENTION")[0];
export const DETAILS = nodes("DETAILS");
export const INLINE_MATH = nodes("INLINE_MATH")[0];
export const BLOCK_MATH = nodes("BLOCK_MATH")[0];
export const TEXT_ALIGN = textAlign();
export const LINK_ATTRS = linkAttrs();
export const IMAGE_SIZE = coreAttrs("IMAGE_SIZE");
export const TABLE_SPANS = coreAttrs("TABLE_SPANS");
