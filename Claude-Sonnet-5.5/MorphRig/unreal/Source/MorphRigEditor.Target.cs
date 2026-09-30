using UnrealBuildTool;

public class MorphRigEditorTarget : TargetRules
{
	public MorphRigEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("MorphRig");
	}
}
