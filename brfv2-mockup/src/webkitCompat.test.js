import { describe, expect, it } from 'vitest';
import { patchFrozenPrototypeAssignments, patchPuckAutoFrame } from './webkitCompat';

describe('Tauri frozen-prototype compatibility', () => {
  it('defines inherited Signals methods as own properties', () => {
    const source = [
      'l.prototype.valueOf=function(){return this.value};',
      'l.prototype.toString=function(){return this.value+""};',
      'l.prototype.toJSON=function(){return this.value};',
    ].join('');

    expect(patchFrozenPrototypeAssignments(source)).toBe(
      'Object.defineProperty(l.prototype,"valueOf",{value:function(){return this.value},writable:true,configurable:true,enumerable:true});'
      + 'Object.defineProperty(l.prototype,"toString",{value:function(){return this.value+""},writable:true,configurable:true,enumerable:true});'
      + 'Object.defineProperty(l.prototype,"toJSON",{value:function(){return this.value},writable:true,configurable:true,enumerable:true});',
    );
  });

  it('handles a dependency function with nested blocks', () => {
    const source = 'f.prototype.toString=function(input){if(input){return "yes"}return "no"},f.prototype.toJSON=function(){return {ok:true}};';
    expect(patchFrozenPrototypeAssignments(source)).toBe(
      'Object.defineProperty(f.prototype,"toString",{value:function(input){if(input){return "yes"}return "no"},writable:true,configurable:true,enumerable:true}),'
      + 'Object.defineProperty(f.prototype,"toJSON",{value:function(){return {ok:true}},writable:true,configurable:true,enumerable:true});',
    );
  });

  it('does not rewrite unrelated prototype methods', () => {
    const source = 'l.prototype.subscribe=function(){return this.value};';
    expect(patchFrozenPrototypeAssignments(source)).toBe(source);
  });

  it('activates a completed Puck srcdoc when WebKit skipped load', () => {
    const source = '  }, [frameRef, loaded, stylesLoaded]);\n  return /* @__PURE__ */ jsx43(\n    "iframe",';
    const patched = patchPuckAutoFrame(source);
    expect(patched).toContain('doc?.getElementById("frame-root")');
    expect(patched).toContain('setLoaded(true)');
  });
});
