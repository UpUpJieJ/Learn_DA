import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import AppButton from "../AppButton.vue";
import AppInput from "../AppInput.vue";
import ConfirmDialog from "../ConfirmDialog.vue";
import CodeOutput from "../CodeOutput.vue";
import ToastHost from "../ToastHost.vue";
import { useToast } from "@/composables/useToast";

const wrappers: ReturnType<typeof mount>[] = [];
function render(component: any, options: any) {
    const w = mount(component, options); wrappers.push(w); return w;
}
afterEach(() => {
    wrappers.splice(0).forEach(w => w.unmount());
    document.body.innerHTML = ""; useToast().clear(); vi.restoreAllMocks(); vi.useRealTimers();
});
describe("shared UI resilience", () => {
    it("keeps a loading button focusable but blocks clicks", async () => {
        const w = render(AppButton, {props: {loading: true}});
        expect(w.attributes("disabled")).toBeUndefined();
        expect(w.attributes("aria-disabled")).toBe("true");
        await w.trigger("click"); expect(w.emitted("click")).toBeUndefined();
    });
    it("forwards native input attributes and only references rendered descriptions", async () => {
        const blur = vi.fn();
        const w = render(AppInput, {props: {modelValue:"", hint:"hint", error:"error"}, attrs:{name:"query", autocomplete:"off", onBlur:blur}});
        const input = w.find("input");
        expect(input.attributes("name")).toBe("query");
        await input.trigger("blur"); expect(blur).toHaveBeenCalledOnce();
        for (const id of input.attributes("aria-describedby")!.split(" ")) expect(w.find(`[id="${id}"]`).exists()).toBe(true);
    });
    it("traps focus, locks scrolling and restores the opener", async () => {
        const opener = document.createElement("button"); document.body.append(opener); opener.focus();
        const w = render(ConfirmDialog, {attachTo:document.body,props:{open:true,title:"Confirm",confirmText:"Delete"}});
        await nextTick();
        expect(document.body.style.overflow).toBe("hidden");
        const buttons = document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button');
        buttons[1]!.focus(); window.dispatchEvent(new KeyboardEvent("keydown",{key:"Tab",cancelable:true}));
        expect(document.activeElement).toBe(buttons[0]);
        await w.setProps({open:false}); expect(document.activeElement).toBe(opener);
        expect(document.body.style.overflow).not.toBe("hidden");
    });
    it("latches confirmation and ignores cancellation while loading", async () => {
        const w = render(ConfirmDialog, {props:{open:true,title:"Confirm",confirmText:"Delete"}});
        await nextTick();
        const button = document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')[1]!;
        button.click(); button.click();
        expect(w.emitted("confirm")).toHaveLength(1);
        await w.setProps({loading:true});
        window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}));
        expect(w.emitted("cancel")).toBeUndefined();
    });
    it("renders stdout and stderr together and copies over HTTP", async () => {
        Object.defineProperty(navigator,"clipboard",{configurable:true,value:undefined});
        const copy = vi.fn().mockReturnValue(true);
        Object.defineProperty(document,"execCommand",{configurable:true,value:copy});
        const w = render(CodeOutput,{props:{stdout:"normal output",stderr:"error output",status:"error"}});
        expect(w.text()).toContain("normal output"); expect(w.text()).toContain("error output");
        expect(w.find('[role="log"]').attributes("aria-live")).toBe("polite");
        await w.find("button").trigger("click"); expect(copy).toHaveBeenCalledWith("copy");
        expect(document.querySelector("textarea")).toBeNull();
    });
    it("bounds the toast queue and cleans evicted timers", () => {
        vi.useFakeTimers(); const toast = useToast();
        for(let i=0;i<20;i++) toast.success(`message ${i}`);
        expect(toast.toasts.value.length).toBeLessThanOrEqual(5);
        expect(vi.getTimerCount()).toBeLessThanOrEqual(5);
        toast.clear(); expect(vi.getTimerCount()).toBe(0);
    });
    it("reports unavailable legacy clipboard without leaving a textarea", async () => {
        Object.defineProperty(navigator,"clipboard",{configurable:true,value:undefined});
        Object.defineProperty(document,"execCommand",{configurable:true,value:undefined});
        const w = render(CodeOutput,{props:{stdout:"output"}});
        await w.find("button").trigger("click");
        expect(useToast().toasts.value.at(-1)?.kind).toBe("error");
        expect(document.querySelector("textarea")).toBeNull();
    });
    it("cleans toast timers when the single toast host unmounts", () => {
        vi.useFakeTimers();
        const host = mount(ToastHost);
        useToast().success("temporary");
        expect(vi.getTimerCount()).toBe(1);
        host.unmount();
        expect(vi.getTimerCount()).toBe(0);
        expect(useToast().toasts.value).toHaveLength(0);
    });
});
