using UnrealBuildTool;
using System.Collections.Generic;
public class MorphRigTarget : TargetRules {
    public MorphRigTarget(TargetInfo Target) : base(Target) {
        Type = TargetType.Game; DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest; ExtraModuleNames.Add("MorphRig");
    }
}
