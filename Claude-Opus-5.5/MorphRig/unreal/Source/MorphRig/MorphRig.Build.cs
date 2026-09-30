using UnrealBuildTool;

public class MorphRig : ModuleRules
{
	public MorphRig(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] {
			"Core", "CoreUObject", "Engine", "InputCore", "AnimationCore", "Slate", "SlateCore", "UMG",
			"Json", "JsonUtilities", "RenderCore", "RHI", "ApplicationCore"
		});
	}
}
