using UnrealBuildTool;
using System.Collections.Generic;
public class MorphRigEditorTarget : TargetRules
{
    public MorphRigEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("MorphRig");
    }
}
